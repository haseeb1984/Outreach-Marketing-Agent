"""Workspace invitations with hashed one-use tokens and email-bound acceptance."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings
from app.services.auth_security import new_opaque_token, normalize_email, token_digest
from app.services.email_delivery import EmailDeliveryFailed, EmailDeliveryNotConfigured, SMTPEmailDelivery

router = APIRouter(prefix="/api/v1/workspaces/invitations", tags=["workspace invitations"])


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    role: str = "member"

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in {"admin", "member", "viewer"}:
            raise ValueError("invalid_invitation_role")
        return value


class InvitationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=512)


async def _authorize_admin(request: Request, workspace_id: str, session: dict) -> None:
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role="admin"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="workspace_service_not_configured")
    return pool


@router.get("")
async def list_invitations(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    _, _, session = await _authenticated(request)
    await _authorize_admin(request, workspace_id, session)
    try:
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT id,workspace_id,invited_email,role,status,invited_by,
                          created_at,expires_at,accepted_at,revoked_at
                   FROM workspace_invitations WHERE workspace_id=$1
                   ORDER BY created_at DESC LIMIT 100""",
                workspace_id,
            )
        items = []
        for row in rows:
            item = dict(row)
            item["id"] = str(item["id"])
            item["invited_by"] = str(item["invited_by"])
            items.append(item)
        return {"items": items}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="invitation_list_unavailable") from None


@router.post("", status_code=202)
async def create_invitation(payload: InvitationCreate, request: Request) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize_admin(request, payload.workspace_id, session)
    if not settings.frontend_public_url:
        raise HTTPException(status_code=503, detail="frontend_public_url_not_configured")
    try:
        email = normalize_email(payload.email)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_invitation_email") from None

    token = new_opaque_token()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=7)
    pool = _pool(request)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """UPDATE workspace_invitations SET status='revoked',revoked_at=$3
                       WHERE workspace_id=$1 AND invited_email=$2 AND status='pending'""",
                    payload.workspace_id, email, now,
                )
                row = await conn.fetchrow(
                    """INSERT INTO workspace_invitations
                       (workspace_id,invited_email,role,token_sha256,status,invited_by,created_at,expires_at)
                       VALUES ($1,$2,$3,$4,'pending',$5,$6,$7)
                       RETURNING id""",
                    payload.workspace_id, email, payload.role, token_digest(token),
                    UUID(str(session["user_id"])), now, expires_at,
                )
                invitation_id = row["id"]
        try:
            await SMTPEmailDelivery().send_workspace_invitation_email(
                recipient=email, token=token, workspace_name="Workspace",
                role=payload.role, expires_at=expires_at,
            )
        except (EmailDeliveryFailed, EmailDeliveryNotConfigured, ValueError):
            async with pool.acquire() as conn:
                await conn.execute(
                    """UPDATE workspace_invitations SET status='revoked',revoked_at=now()
                       WHERE id=$1 AND status='pending'""",
                    invitation_id,
                )
            raise HTTPException(status_code=503, detail="invitation_email_delivery_failed") from None
        return {"message": "Invitation email sent.", "email": email, "role": payload.role, "expires_at": expires_at.isoformat()}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="invitation_create_unavailable") from None


@router.post("/accept")
async def accept_invitation(payload: InvitationAccept, request: Request) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    now = datetime.now(timezone.utc)
    try:
        digest = token_digest(payload.token)
    except ValueError:
        raise HTTPException(status_code=400, detail="invitation_invalid_or_expired") from None
    pool = _pool(request)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                invitation = await conn.fetchrow(
                    """SELECT id,workspace_id,invited_email,role,status,expires_at
                       FROM workspace_invitations WHERE token_sha256=$1 FOR UPDATE""",
                    digest,
                )
                if invitation is None or invitation["status"] != "pending":
                    raise HTTPException(status_code=400, detail="invitation_invalid_or_expired")
                if invitation["expires_at"] <= now:
                    await conn.execute(
                        "UPDATE workspace_invitations SET status='expired' WHERE id=$1",
                        invitation["id"],
                    )
                    raise HTTPException(status_code=410, detail="invitation_expired")
                if invitation["invited_email"] != normalize_email(session["email"]):
                    raise HTTPException(status_code=403, detail="invitation_email_mismatch")
                existing = await conn.fetchrow(
                    """SELECT status FROM workspace_memberships
                       WHERE workspace_id=$1 AND user_id=$2 FOR UPDATE""",
                    invitation["workspace_id"], UUID(str(session["user_id"])),
                )
                if existing is not None and existing["status"] == "active":
                    raise HTTPException(status_code=409, detail="already_workspace_member")
                await conn.execute(
                    """INSERT INTO workspace_memberships (workspace_id,user_id,role,status,created_at,updated_at)
                       VALUES ($1,$2,$3,'active',$4,$4)
                       ON CONFLICT (workspace_id,user_id) DO UPDATE SET
                         role=EXCLUDED.role,status='active',updated_at=EXCLUDED.updated_at""",
                    invitation["workspace_id"], UUID(str(session["user_id"])),
                    invitation["role"], now,
                )
                await conn.execute(
                    """UPDATE workspace_invitations SET status='accepted',accepted_at=$2
                       WHERE id=$1 AND status='pending'""",
                    invitation["id"], now,
                )
                await conn.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id,actor_user_id,event_type,outcome,metadata,created_at)
                       VALUES ($1,$2,'workspace.invitation.accepted','success',$3::jsonb,$4)""",
                    invitation["workspace_id"], UUID(str(session["user_id"])),
                    '{"role":"' + invitation["role"] + '"}', now,
                )
                return {"workspace_id": invitation["workspace_id"], "role": invitation["role"], "message": "Workspace invitation accepted."}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="invitation_accept_unavailable") from None


@router.delete("/{invitation_id}")
async def revoke_invitation(
    invitation_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize_admin(request, workspace_id, session)
    try:
        async with _pool(request).acquire() as conn:
            result = await conn.execute(
                """UPDATE workspace_invitations SET status='revoked',revoked_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND status='pending'""",
                invitation_id, workspace_id,
            )
    except Exception:
        raise HTTPException(status_code=503, detail="invitation_revoke_unavailable") from None
    if not result.endswith(" 1"):
        raise HTTPException(status_code=404, detail="pending_invitation_not_found")
    return {"revoked": True}
