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
