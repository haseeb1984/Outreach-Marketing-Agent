"""Workspace-scoped CRM prospect endpoints; no crawling or message delivery occurs here."""
from __future__ import annotations

from uuid import UUID
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf, _consume
from app.services.workspace_prospect_store import STAGES

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/prospects", tags=["prospects"])


def _https_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise ValueError("clean_https_url_required")
    return value.strip().rstrip("/")


class ProspectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: UUID
    display_name: str = Field(min_length=1, max_length=200)
    organization_name: str | None = Field(default=None, max_length=200)
    website_url: str = Field(min_length=9, max_length=2048)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=40)
    source_url: str = Field(min_length=9, max_length=2048)
    fit_reason: str = Field(min_length=1, max_length=2000)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("website_url", "source_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        return _https_url(value)

    @field_validator("display_name", "fit_reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field_must_not_be_blank")
        return value.strip()

    @field_validator("contact_phone")
    @classmethod
    def phone_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("phone_must_not_be_blank")
        return value.strip() if value else None


class ProspectStageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: str = Field(pattern="^(researched|qualified|drafting|contacted|replied|meeting|customer|not_a_fit|opted_out)$")
    note: str | None = Field(default=None, max_length=4000)


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
    store = getattr(request.app.state, "workspace_prospect_store", None)
    limiter = getattr(request.app.state, "auth_rate_limiter", None)
    if store is None or limiter is None:
        raise HTTPException(status_code=503, detail="prospects_unavailable")
    return store, limiter, session


@router.get("")
async def list_prospects(
    workspace_id: str, request: Request,
    campaign_id: UUID | None = None,
    stage: str | None = Query(default=None, pattern="^(researched|qualified|drafting|contacted|replied|meeting|customer|not_a_fit|opted_out)$"),
    limit: int = Query(default=50, ge=1, le=100),
):
    store, limiter, session = await _authorized(request, workspace_id, "viewer")
    await _consume(limiter, namespace="prospect-list", identifier=f"{workspace_id}:{session['user_id']}", limit=120, window=3600)
    try:
        rows = await store.list_for_workspace(workspace_id=workspace_id, campaign_id=campaign_id, stage=stage, limit=limit)
    except Exception:
        raise HTTPException(status_code=503, detail="prospects_unavailable") from None
    return {"workspace_id": workspace_id, "prospects": rows}


@router.post("", status_code=201)
async def create_prospect(workspace_id: str, payload: ProspectInput, request: Request):
    store, limiter, session = await _authorized(request, workspace_id, "member")
    _check_csrf(request, session)
    await _consume(limiter, namespace="prospect-create", identifier=f"{workspace_id}:{session['user_id']}", limit=60, window=3600)
    try:
        row = await store.create(workspace_id=workspace_id, user_id=session["user_id"], **payload.model_dump())
    except Exception as exc:
        # Unique-constraint collisions and missing/cross-workspace campaigns are deliberately generic.
        if exc.__class__.__name__ in {"UniqueViolationError", "ForeignKeyViolationError"}:
            raise HTTPException(status_code=409, detail="prospect_conflict_or_campaign_unavailable") from None
        raise HTTPException(status_code=503, detail="prospects_unavailable") from None
    return {"workspace_id": workspace_id, "prospect": row}


@router.post("/{prospect_id}/stage")
async def change_prospect_stage(
    workspace_id: str, prospect_id: UUID, payload: ProspectStageInput, request: Request
):
    store, limiter, session = await _authorized(request, workspace_id, "member")
    _check_csrf(request, session)
    await _consume(limiter, namespace="prospect-stage", identifier=f"{workspace_id}:{session['user_id']}", limit=120, window=3600)
    try:
        row = await store.update_stage(workspace_id=workspace_id, user_id=session["user_id"],
                                       prospect_id=prospect_id, stage=payload.stage, note=payload.note)
    except Exception:
        raise HTTPException(status_code=503, detail="prospects_unavailable") from None
    if row is None:
        raise HTTPException(status_code=404, detail="prospect_not_found")
    return {"workspace_id": workspace_id, "prospect": row,
            "outreach_allowed": not row["opt_out"], "message": "Opt-out is permanent for this prospect record." if row["opt_out"] else "Stage updated."}
