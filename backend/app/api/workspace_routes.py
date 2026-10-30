"""Workspace creation for authenticated multi-tenant accounts."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("workspace_name_required")
        return value


@router.post("", status_code=201)
async def create_workspace(payload: WorkspaceCreate, request: Request) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="workspace_service_not_configured")
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    user_id = UUID(str(session["user_id"]))
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Lock the account row so concurrent creates cannot race the limit check.
                account = await conn.fetchrow(
                    "SELECT id FROM app_users WHERE id=$1 FOR UPDATE", user_id
                )
                if account is None:
                    raise HTTPException(status_code=401, detail="account_unavailable")
                count = await conn.fetchval(
                    "SELECT count(*) FROM workspace_memberships WHERE user_id=$1 AND status='active'",
                    user_id,
                )
                if count >= 10:
                    raise HTTPException(status_code=429, detail="workspace_limit_reached")
                workspace_id = "workspace-" + uuid4().hex
                await conn.execute(
                    "INSERT INTO workspaces (id,name) VALUES ($1,$2)",
                    workspace_id, payload.name,
                )
                await conn.execute(
                    """INSERT INTO workspace_memberships
                       (workspace_id,user_id,role,status,created_at,updated_at)
                       VALUES ($1,$2,'owner','active',now(),now())""",
                    workspace_id, user_id,
                )
                await conn.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id,actor_user_id,event_type,outcome,metadata,created_at)
                       VALUES ($1,$2,'workspace.created','success',$3::jsonb,now())""",
                    workspace_id, user_id, json.dumps({"name": payload.name}),
                )
        return {"workspace_id": workspace_id, "name": payload.name, "role": "owner"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_create_unavailable") from None

class WorkspaceOwnershipTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_user_id: UUID


@router.post("/{workspace_id}/transfer-ownership")
async def transfer_workspace_ownership(
    workspace_id: str,
    payload: WorkspaceOwnershipTransfer,
    request: Request,
) -> dict:
    """Transfer ownership to an existing active member without leaving an ownerless workspace."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="workspace_service_not_configured")
    actor_id = UUID(str(session["user_id"]))
    if not workspace_id.strip() or len(workspace_id) > 200:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    if payload.target_user_id == actor_id:
        raise HTTPException(status_code=422, detail="ownership_transfer_target_must_be_another_member")

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                workspace = await conn.fetchrow(
                    "SELECT id FROM workspaces WHERE id=$1 FOR UPDATE", workspace_id
                )
                if workspace is None:
                    raise HTTPException(status_code=404, detail="workspace_not_found")
                actor = await conn.fetchrow(
                    """SELECT role,status FROM workspace_memberships
                       WHERE workspace_id=$1 AND user_id=$2 FOR UPDATE""",
                    workspace_id, actor_id,
                )
                if actor is None or actor["status"] != "active":
                    raise HTTPException(status_code=404, detail="workspace_not_found")
                if actor["role"] != "owner":
                    raise HTTPException(status_code=403, detail="workspace_owner_required")
                target = await conn.fetchrow(
                    """SELECT m.role,m.status FROM workspace_memberships m
                       JOIN app_users u ON u.id=m.user_id
                       WHERE m.workspace_id=$1 AND m.user_id=$2
                         AND u.status='active' AND u.email_verified_at IS NOT NULL
                       FOR UPDATE OF m""",
                    workspace_id, payload.target_user_id,
                )
                if target is None or target["status"] != "active":
                    raise HTTPException(status_code=404, detail="workspace_member_not_found")
                if target["role"] == "owner":
                    raise HTTPException(status_code=409, detail="workspace_already_owned_by_target")
                await conn.execute(
                    """UPDATE workspace_memberships SET role='admin',updated_at=now()
                       WHERE workspace_id=$1 AND user_id=$2 AND role='owner' AND status='active'""",
                    workspace_id, actor_id,
                )
                await conn.execute(
                    """UPDATE workspace_memberships SET role='owner',updated_at=now()
                       WHERE workspace_id=$1 AND user_id=$2 AND status='active'""",
                    workspace_id, payload.target_user_id,
                )
                await conn.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id,actor_user_id,event_type,outcome,metadata,created_at)
                       VALUES ($1,$2,'workspace.ownership.transferred','success',$3::jsonb,now())""",
                    workspace_id, actor_id,
                    json.dumps({"previous_owner_user_id": str(actor_id),
                                "new_owner_user_id": str(payload.target_user_id)}),
                )
        return {
            "workspace_id": workspace_id,
            "previous_owner_user_id": str(actor_id),
            "new_owner_user_id": str(payload.target_user_id),
            "previous_owner_role": "admin",
            "new_owner_role": "owner",
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_ownership_transfer_unavailable") from None

