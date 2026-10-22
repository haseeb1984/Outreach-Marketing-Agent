"""Workspace membership administration with role and ownership safeguards."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf

router = APIRouter(prefix="/api/v1/workspaces/members", tags=["workspace membership"])


class MemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    role: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        if value not in {"admin", "member", "viewer"}:
            raise ValueError("invalid_member_role")
        return value


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="workspace_service_not_configured")
    return pool


async def _authorized_session(request: Request, workspace_id: str, *, csrf: bool = False) -> dict:
    _, _, session = await _authenticated(request)
    if csrf:
        _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role="admin"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    return session


@router.get("")
async def list_workspace_members(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    await _authorized_session(request, workspace_id)
    try:
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT m.user_id::text AS user_id,u.email,m.role,m.status,m.created_at,m.updated_at
                   FROM workspace_memberships m JOIN app_users u ON u.id=m.user_id
                   WHERE m.workspace_id=$1 AND m.status IN ('active','suspended')
                   ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 WHEN 'member' THEN 2 ELSE 3 END,u.email""",
                workspace_id,
            )
        return {"items": [dict(row) for row in rows]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_members_unavailable") from None


@router.patch("/{user_id}")
async def update_workspace_member(user_id: UUID, payload: MemberRoleUpdate, request: Request) -> dict:
    actor = await _authorized_session(request, payload.workspace_id, csrf=True)
    pool = _pool(request)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                actor_role = await conn.fetchval(
                    """SELECT role FROM workspace_memberships
                       WHERE workspace_id=$1 AND user_id=$2 AND status='active'""",
                    payload.workspace_id, UUID(str(actor["user_id"])),
                )
                target = await conn.fetchrow(
                    """SELECT role,status FROM workspace_memberships
                       WHERE workspace_id=$1 AND user_id=$2 FOR UPDATE""",
                    payload.workspace_id, user_id,
                )
                if target is None or target["status"] != "active":
                    raise HTTPException(status_code=404, detail="workspace_member_not_found")
                if target["role"] == "owner":
                    raise HTTPException(status_code=409, detail="workspace_owner_role_is_protected")
                if payload.role == "admin" and actor_role != "owner":
                    raise HTTPException(status_code=403, detail="only_owner_can_grant_admin")
                if target["role"] == "admin" and actor_role != "owner":
                    raise HTTPException(status_code=403, detail="only_owner_can_change_admin")
                await conn.execute(
                    """UPDATE workspace_memberships SET role=$3,updated_at=now()
                       WHERE workspace_id=$1 AND user_id=$2""",
                    payload.workspace_id, user_id, payload.role,
                )
                await conn.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id,actor_user_id,event_type,outcome,metadata,created_at)
                       VALUES ($1,$2,'workspace.member.role_changed','success',$3::jsonb,now())""",
                    payload.workspace_id, UUID(str(actor["user_id"])),
                    json.dumps({"target_user_id": str(user_id), "role": payload.role}),
                )
        return {"workspace_id": payload.workspace_id, "user_id": str(user_id), "role": payload.role}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_member_update_unavailable") from None


@router.delete("/{user_id}")
async def remove_workspace_member(
    user_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    actor = await _authorized_session(request, workspace_id, csrf=True)
    pool = _pool(request)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                actor_id = UUID(str(actor["user_id"]))
                actor_role = await conn.fetchval(
                    """SELECT role FROM workspace_memberships
                       WHERE workspace_id=$1 AND user_id=$2 AND status='active'""",
                    workspace_id, actor_id,
                )
                target = await conn.fetchrow(
                    """SELECT role,status FROM workspace_memberships
                       WHERE workspace_id=$1 AND user_id=$2 FOR UPDATE""",
                    workspace_id, user_id,
                )
                if target is None or target["status"] != "active":
                    raise HTTPException(status_code=404, detail="workspace_member_not_found")
                if target["role"] == "owner":
                    raise HTTPException(status_code=409, detail="workspace_owner_cannot_be_removed")
                if target["role"] == "admin" and actor_role != "owner":
                    raise HTTPException(status_code=403, detail="only_owner_can_remove_admin")
                await conn.execute(
                    """UPDATE workspace_memberships SET status='revoked',updated_at=now()
                       WHERE workspace_id=$1 AND user_id=$2""",
                    workspace_id, user_id,
                )
                await conn.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id,actor_user_id,event_type,outcome,metadata,created_at)
                       VALUES ($1,$2,'workspace.member.removed','success',$3::jsonb,now())""",
                    workspace_id, actor_id, json.dumps({"target_user_id": str(user_id)}),
                )
        return {"workspace_id": workspace_id, "user_id": str(user_id), "removed": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_member_remove_unavailable") from None
