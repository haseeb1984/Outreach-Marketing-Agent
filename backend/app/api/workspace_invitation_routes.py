"""Workspace invitations with hashed one-use tokens and email-bound acceptance."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings
from app.services.auth_security import new_opaque_token, normalize_email, token_digest
from app.services.email_delivery import SMTPEmailDelivery

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
                """SELECT id,workspace_id,invited_email,role,
                          CASE WHEN status='pending' AND expires_at <= now() THEN 'expired' ELSE status END AS status,invited_by,
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
    if not (settings.frontend_public_url or settings.frontend_origins.strip()):
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
                workspace = await conn.fetchrow(
                    "SELECT id FROM workspaces WHERE id=$1 FOR UPDATE",
                    payload.workspace_id,
                )
                if workspace is None:
                    raise HTTPException(status_code=404, detail="workspace_not_found")
                actor_id = UUID(str(session["user_id"]))
                actor_role = await conn.fetchval(
                    """SELECT role FROM workspace_memberships
                       WHERE workspace_id=$1 AND user_id=$2 AND status='active' FOR UPDATE""",
                    payload.workspace_id, actor_id,
                )
                if actor_role not in {"owner", "admin"}:
                    raise HTTPException(status_code=404, detail="workspace_not_found")
                if payload.role == "admin" and actor_role != "owner":
                    raise HTTPException(status_code=403, detail="only_owner_can_invite_admin")
                workspace_name = workspace["name"] if "name" in workspace else await conn.fetchval(
                    "SELECT name FROM workspaces WHERE id=$1", payload.workspace_id
                )
                existing_member = await conn.fetchval(
                    """SELECT m.status FROM workspace_memberships m JOIN app_users u ON u.id=m.user_id
                       WHERE m.workspace_id=$1 AND u.email=$2 FOR UPDATE OF m""",
                    payload.workspace_id, email,
                )
                if existing_member == "active":
                    raise HTTPException(status_code=409, detail="already_workspace_member")
                replaced = await conn.fetch(
                    """UPDATE workspace_invitations SET status='revoked',revoked_at=$3
                       WHERE workspace_id=$1 AND invited_email=$2 AND status='pending'
                       RETURNING id""",
                    payload.workspace_id, email, now,
                )
                for old_invitation in replaced:
                    await conn.execute(
                        """INSERT INTO security_audit_events
                           (workspace_id,actor_user_id,event_type,outcome,metadata,created_at)
                           VALUES ($1,$2,'workspace.invitation.revoked','success',$3::jsonb,$4)""",
                        payload.workspace_id, actor_id,
                        json.dumps({"invitation_id": str(old_invitation["id"]), "reason": "replaced"}),
                        now,
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
                await conn.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id,actor_user_id,event_type,outcome,metadata,created_at)
                       VALUES ($1,$2,'workspace.invitation.created','success',$3::jsonb,$4)""",
                    payload.workspace_id, actor_id,
                    json.dumps({"invitation_id": str(invitation_id), "email": email, "role": payload.role, "expires_at": expires_at.isoformat()}),
                    now,
                )
        try:
            await SMTPEmailDelivery().send_workspace_invitation_email(
                recipient=email, token=token, workspace_name=workspace_name or "Workspace",
                role=payload.role, expires_at=expires_at,
            )
        except Exception:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """UPDATE workspace_invitations SET status='revoked',revoked_at=now()
                           WHERE id=$1 AND status='pending'""",
                        invitation_id,
                    )
                    await conn.execute(
                        """INSERT INTO security_audit_events
                           (workspace_id,actor_user_id,event_type,outcome,metadata,created_at)
                           VALUES ($1,$2,'workspace.invitation.email_failed','failure',$3::jsonb,now())""",
                        payload.workspace_id, UUID(str(session["user_id"])),
                        json.dumps({"invitation_id": str(invitation_id)}),
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
                    # Do not raise inside the transaction: that would roll back the
                    # status change and leave the expired bearer token pending forever.
                    await conn.execute(
                        "UPDATE workspace_invitations SET status='expired',revoked_at=$2 WHERE id=$1",
                        invitation["id"], now,
                    )
                    await conn.execute(
                        """INSERT INTO security_audit_events
                           (workspace_id,actor_user_id,event_type,outcome,metadata,created_at)
                           VALUES ($1,$2,'workspace.invitation.expired','failure',$3::jsonb,$4)""",
                        invitation["workspace_id"], None,
                        json.dumps({"invitation_id": str(invitation["id"])}), now,
                    )
                    expired_invitation = True
                else:
                    expired_invitation = False
                if not expired_invitation:
                    if invitation["invited_email"] != normalize_email(session["email"]):
                        raise HTTPException(status_code=403, detail="invitation_email_mismatch")
                    # Serialize invitation acceptance for this account with workspace creation.
                    account = await conn.fetchrow(
                        "SELECT id,status,email_verified_at FROM app_users WHERE id=$1 FOR UPDATE",
                        UUID(str(session["user_id"])),
                    )
                    if account is None or account["status"] != "active":
                        raise HTTPException(status_code=401, detail="account_unavailable")
                    if account["email_verified_at"] is None:
                        raise HTTPException(status_code=403, detail="email_verification_required")
                    active_memberships = await conn.fetchval(
                        """SELECT count(*) FROM workspace_memberships
                           WHERE user_id=$1 AND status='active'""",
                        UUID(str(session["user_id"])),
                    )
                    if active_memberships >= 10:
                        raise HTTPException(status_code=429, detail="workspace_limit_reached")
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
        if expired_invitation:
            raise HTTPException(status_code=410, detail="invitation_expired")
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
            async with conn.transaction():
                actor_id = UUID(str(session["user_id"]))
                actor_role = await conn.fetchval(
                    """SELECT role FROM workspace_memberships
                       WHERE workspace_id=$1 AND user_id=$2 AND status='active' FOR UPDATE""",
                    workspace_id, actor_id,
                )
                if actor_role not in {"owner", "admin"}:
                    raise HTTPException(status_code=404, detail="workspace_not_found")
                result = await conn.execute(
                    """UPDATE workspace_invitations SET status='revoked',revoked_at=now()
                       WHERE id=$1 AND workspace_id=$2 AND status='pending'""",
                    invitation_id, workspace_id,
                )
                if not result.endswith(" 1"):
                    raise HTTPException(status_code=404, detail="pending_invitation_not_found")
                await conn.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id,actor_user_id,event_type,outcome,metadata,created_at)
                       VALUES ($1,$2,'workspace.invitation.revoked','success',$3::jsonb,now())""",
                    workspace_id, actor_id,
                    json.dumps({"invitation_id": str(invitation_id)}),
                )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="invitation_revoke_unavailable") from None
    return {"revoked": True}
