"""Authenticated, workspace-scoped campaign metadata endpoints.

Creating a campaign never fetches the target website or sends outreach.
"""
from __future__ import annotations

from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf, _consume

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/campaigns", tags=["campaigns"])
GOALS = {"partnerships", "influencer_outreach", "sales", "brand_awareness", "other"}
CHANNELS = {"email", "whatsapp", "multi_channel"}
STATUSES = {"draft", "active", "paused", "completed", "archived"}


class CampaignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    website_url: str = Field(min_length=9, max_length=2048)
    goal: str = Field(pattern="^(partnerships|influencer_outreach|sales|brand_awareness|other)$")
    channel: str = Field(pattern="^(email|whatsapp|multi_channel)$")

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name_must_not_be_blank")
        return value.strip()

    @field_validator("website_url")
    @classmethod
    def safe_https_url(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        if (parsed.scheme.lower() != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise ValueError("website_url_must_be_clean_https_url")
        return value.strip().rstrip("/")


async def _authorized(request: Request, workspace_id: str, role: str):
    store, _, session = await _authenticated(request)
    if not workspace_id.strip() or len(workspace_id) > 200:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    try:
        allowed = await store.authorize_workspace(
            user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
        )
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_authorization_unavailable") from None
    if not allowed:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    campaigns = getattr(request.app.state, "workspace_campaign_store", None)
    limiter = getattr(request.app.state, "auth_rate_limiter", None)
    if campaigns is None or limiter is None:
        raise HTTPException(status_code=503, detail="campaigns_unavailable")
    return campaigns, limiter, session


@router.get("")
async def list_campaigns(
    workspace_id: str, request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    status: str | None = Query(default=None, pattern="^(draft|active|paused|completed|archived)$"),
):
    campaigns, limiter, session = await _authorized(request, workspace_id, "viewer")
    await _consume(limiter, namespace="campaign-list",
                   identifier=f"{workspace_id}:{session['user_id']}", limit=120, window=3600)
    try:
        rows = await campaigns.list_for_workspace(workspace_id=workspace_id, limit=limit, status=status)
    except Exception:
        raise HTTPException(status_code=503, detail="campaigns_unavailable") from None
    return {"workspace_id": workspace_id, "campaigns": rows}


@router.post("", status_code=201)
async def create_campaign(workspace_id: str, payload: CampaignInput, request: Request):
    campaigns, limiter, session = await _authorized(request, workspace_id, "member")
    _check_csrf(request, session)
    await _consume(limiter, namespace="campaign-create",
                   identifier=f"{workspace_id}:{session['user_id']}", limit=30, window=3600)
    try:
        row = await campaigns.create(
            workspace_id=workspace_id, user_id=session["user_id"], **payload.model_dump()
        )
    except Exception:
        raise HTTPException(status_code=503, detail="campaigns_unavailable") from None
    return {"workspace_id": workspace_id, "campaign": row}


class CampaignStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(draft|active|paused|completed|archived)$")


@router.post("/{campaign_id}/status")
async def transition_campaign_status(
    workspace_id: str, campaign_id: UUID,
    payload: CampaignStatusInput, request: Request,
):
    campaigns, limiter, session = await _authorized(request, workspace_id, "admin")
    _check_csrf(request, session)
    await _consume(
        limiter, namespace="campaign-status",
        identifier=f"{workspace_id}:{session['user_id']}", limit=60, window=3600,
    )
    try:
        row = await campaigns.transition_status(
            workspace_id=workspace_id, campaign_id=campaign_id,
            user_id=session["user_id"], status=payload.status,
        )
    except ValueError as exc:
        if str(exc) in {"invalid_campaign_transition", "campaign_status_unchanged", "invalid_campaign_status"}:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        raise HTTPException(status_code=422, detail="invalid_campaign_status") from None
    except Exception:
        raise HTTPException(status_code=503, detail="campaigns_unavailable") from None
    if row is None:
        raise HTTPException(status_code=404, detail="campaign_not_found")
    return {"workspace_id": workspace_id, "campaign": row}
