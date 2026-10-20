"""Workspace-scoped provider connection intent and safe metadata endpoints.

No OAuth callback, provider API call, token storage, or message sending is implemented here.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf, _consume

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/provider-connections",
    tags=["provider-connections"],
)


class ProviderConnectionIntentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(pattern="^(email|whatsapp)$")
    display_label: str = Field(min_length=1, max_length=160)

    @field_validator("display_label")
    @classmethod
    def label_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("display_label_must_not_be_blank")
        return value.strip()


async def _authorized(request: Request, workspace_id: str, role: str):
    auth_store, _, session = await _authenticated(request)
    if not workspace_id.strip() or len(workspace_id) > 200:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    try:
        allowed = await auth_store.authorize_workspace(
            user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
        )
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_authorization_unavailable") from None
    if not allowed:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    store = getattr(request.app.state, "workspace_provider_connection_store", None)
    limiter = getattr(request.app.state, "auth_rate_limiter", None)
    if store is None or limiter is None:
        raise HTTPException(status_code=503, detail="provider_connections_unavailable")
    return store, limiter, session


@router.get("")
async def list_provider_connections(
    workspace_id: str, request: Request,
    limit: int = Query(default=50, ge=1, le=100),
):
    store, limiter, session = await _authorized(request, workspace_id, "viewer")
    await _consume(limiter, namespace="provider-connection-list",
                   identifier=f"{workspace_id}:{session['user_id']}", limit=120, window=3600)
    try:
        rows = await store.list_for_workspace(workspace_id=workspace_id, limit=limit)
    except Exception:
        raise HTTPException(status_code=503, detail="provider_connections_unavailable") from None
    return {"workspace_id": workspace_id, "connections": rows,
            "sending_enabled": False}


@router.post("", status_code=201)
async def create_provider_connection_intent(
    workspace_id: str, payload: ProviderConnectionIntentInput, request: Request,
):
    store, limiter, session = await _authorized(request, workspace_id, "admin")
    _check_csrf(request, session)
    await _consume(limiter, namespace="provider-connection-intent",
                   identifier=f"{workspace_id}:{session['user_id']}", limit=20, window=3600)
    try:
        row = await store.create_pending(
            workspace_id=workspace_id, user_id=session["user_id"],
            provider=payload.provider, display_label=payload.display_label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="provider_connections_unavailable") from None
    return {
        "workspace_id": workspace_id,
        "connection": row,
        "message": "Intent saved only. Provider authorization and validation are not yet available; sending remains disabled.",
    }



@router.post("/{connection_id}/cancel")
async def cancel_provider_connection_intent(
    workspace_id: str, connection_id: UUID, request: Request,
):
    store, limiter, session = await _authorized(request, workspace_id, "admin")
    _check_csrf(request, session)
    await _consume(limiter, namespace="provider-connection-cancel",
                   identifier=f"{workspace_id}:{session['user_id']}", limit=20, window=3600)
    try:
        row = await store.cancel_pending(
            workspace_id=workspace_id, connection_id=connection_id,
            user_id=session["user_id"],
        )
    except Exception:
        raise HTTPException(status_code=503, detail="provider_connections_unavailable") from None
    if row is None:
        raise HTTPException(status_code=404, detail="pending_connection_intent_not_found")
    return {
        "workspace_id": workspace_id,
        "connection": row,
        "message": "Pending intent cancelled. This endpoint does not revoke credentials at a provider because no live provider connection is supported yet.",
    }
