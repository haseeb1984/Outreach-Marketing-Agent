"""Workspace-scoped outreach draft and human-review endpoints.

Approval records a human decision only; it never sends an email or WhatsApp message.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf, _consume

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/outreach-drafts",
    tags=["outreach drafts"],
)


class OutreachDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: str = Field(pattern="^(email|whatsapp)$")
    client_business: str = Field(min_length=1, max_length=200)
    client_offer: str = Field(min_length=1, max_length=500)
    prospect_name: str = Field(min_length=1, max_length=200)
    prospect_evidence_url: str = Field(min_length=9, max_length=2048)
    verified_relevance: str = Field(min_length=1, max_length=1000)
    verified_facts: list[str] = Field(min_length=1, max_length=10)
    call_to_action: str = Field(min_length=1, max_length=300)
    whatsapp_opt_in_confirmed: bool = False

    @field_validator("verified_facts")
    @classmethod
    def validate_verified_facts(cls, values: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 500 for item in values):
            raise ValueError("verified_facts_items_must_be_1_to_500_characters")
        return values


class DraftReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=1000)


async def _authorized(request: Request, workspace_id: str, role: str):
    store, _, session = await _authenticated(request)
    if not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    try:
        allowed = await store.authorize_workspace(
            user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
        )
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_authorization_unavailable") from None
    if not allowed:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    drafts = getattr(request.app.state, "workspace_outreach_draft_store", None)
    limiter = getattr(request.app.state, "auth_rate_limiter", None)
    if drafts is None or limiter is None:
        raise HTTPException(status_code=503, detail="outreach_drafts_unavailable")
    return drafts, limiter, session


@router.get("")
async def list_outreach_drafts(
    workspace_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    status: str | None = Query(default=None, pattern="^(draft_requires_human_review|approved|rejected)$"),
):
    drafts, limiter, session = await _authorized(request, workspace_id, "viewer")
    await _consume(
        limiter, namespace="outreach-draft-list",
        identifier=f"{workspace_id}:{session['user_id']}", limit=120, window=3600,
    )
    try:
        rows = await drafts.list_for_workspace(workspace_id=workspace_id, limit=limit, status=status)
    except Exception:
        raise HTTPException(status_code=503, detail="outreach_drafts_unavailable") from None
    return {"workspace_id": workspace_id, "drafts": rows}


@router.post("", status_code=201)
async def create_outreach_draft(
    workspace_id: str, payload: OutreachDraftInput, request: Request
):
    drafts, limiter, session = await _authorized(request, workspace_id, "member")
    _check_csrf(request, session)
    if payload.channel == "whatsapp" and not payload.whatsapp_opt_in_confirmed:
        raise HTTPException(status_code=422, detail="whatsapp_opt_in_required")
    await _consume(
        limiter, namespace="outreach-draft-create",
        identifier=f"{workspace_id}:{session['user_id']}", limit=30, window=3600,
    )
    try:
        row = await drafts.create(
            workspace_id=workspace_id, user_id=session["user_id"], **payload.model_dump()
        )
    except ValueError as exc:
        code = str(exc)
        if code.startswith("missing required fields") or code.startswith("channel must"):
            raise HTTPException(status_code=422, detail="invalid_outreach_draft") from None
        raise HTTPException(status_code=422, detail="outreach_draft_rejected") from None
    except Exception:
        raise HTTPException(status_code=503, detail="outreach_drafts_unavailable") from None
    return {"workspace_id": workspace_id, "draft": row}


@router.post("/{draft_id}/review")
async def review_outreach_draft(
    workspace_id: str, draft_id: UUID, payload: DraftReviewInput, request: Request
):
    drafts, limiter, session = await _authorized(request, workspace_id, "admin")
    _check_csrf(request, session)
    await _consume(
        limiter, namespace="outreach-draft-review",
        identifier=f"{workspace_id}:{session['user_id']}", limit=60, window=3600,
    )
    try:
        row = await drafts.review(
            workspace_id=workspace_id, draft_id=draft_id,
            reviewer_id=session["user_id"], decision=payload.decision, note=payload.note,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="outreach_drafts_unavailable") from None
    if row is None:
        raise HTTPException(status_code=409, detail="draft_not_pending_review")
    return {
        "workspace_id": workspace_id,
        "draft": row,
        "delivery_status": "not_sent",
        "message": "Review decision recorded. No message was sent.",
    }
