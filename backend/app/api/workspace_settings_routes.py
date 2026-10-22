"""Workspace display settings with owner/admin authorization."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf

router = APIRouter(prefix="/api/v1/workspaces/settings", tags=["workspace settings"])


class WorkspaceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("workspace_name_required")
        return value


async def _authorized(request: Request, workspace_id: str, *, write: bool = False) -> dict:
    _, _, session = await _authenticated(request)
    if write:
        _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    role = "admin" if write else "viewer"
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    return session


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="workspace_service_not_configured")
    return pool


@router.get("")
async def get_workspace_settings(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    await _authorized(request, workspace_id)
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id,name,created_at FROM workspaces WHERE id=$1",
                workspace_id,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="workspace_not_found")
        return {"workspace_id": row["id"], "name": row["name"], "created_at": row["created_at"]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_settings_unavailable") from None


@router.patch("")
async def update_workspace_settings(payload: WorkspaceSettingsUpdate, request: Request) -> dict:
    await _authorized(request, payload.workspace_id, write=True)
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE workspaces SET name=$2 WHERE id=$1 RETURNING id,name,created_at",
                payload.workspace_id, payload.name,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="workspace_not_found")
        return {"workspace_id": row["id"], "name": row["name"], "created_at": row["created_at"]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_settings_update_unavailable") from None
