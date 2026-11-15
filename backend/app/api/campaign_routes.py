"""Workspace-authorized campaigns and human-reviewed outreach draft queue."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings
from app.services.ai_outreach import AIOutreachUnavailable, generate_ai_outreach

router = APIRouter(prefix="/api/v1", tags=["campaigns"])


def _store(request: Request):
    store = getattr(request.app.state, "campaign_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="campaign_service_not_configured")
    return store


async def _authorize(request: Request, workspace_id: str, role: str, session: dict):
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    allowed = await auth_store.authorize_workspace(user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role)
    if not allowed:
        raise HTTPException(status_code=404, detail="workspace_not_found")


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    client_business: str = Field(min_length=1, max_length=240)
    client_offer: str = Field(min_length=1, max_length=2000)
    target_customer_profile: str = Field(min_length=1, max_length=2000)


class CampaignUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    client_business: str = Field(min_length=1, max_length=240)
    client_offer: str = Field(min_length=1, max_length=2000)
    target_customer_profile: str = Field(min_length=1, max_length=2000)
    status: str = "draft"

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"draft", "active", "paused", "archived"}:
            raise ValueError("invalid_campaign_status")
        return value


class DraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    campaign_id: UUID
    prospect_id: UUID
    channel: str
    call_to_action: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=180, pattern=r"^[A-Za-z0-9._:-]+$")

    @field_validator("channel")
    @classmethod
    def valid_channel(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"email", "whatsapp"}:
            raise ValueError("invalid_channel")
        return value


class DraftRegenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    call_to_action: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=180, pattern=r"^[A-Za-z0-9._:-]+$")


class DraftReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    decision: str
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, value: str) -> str:
        if value not in {"approved", "rejected"}:
            raise ValueError("invalid_decision")
        return value


@router.post("/campaigns", status_code=201)
async def create_campaign(payload: CampaignCreate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    try:
        return await _store(request).create_campaign(
            workspace_id=payload.workspace_id, created_by=session["user_id"],
            name=payload.name, client_business=payload.client_business,
            client_offer=payload.client_offer, target_customer_profile=payload.target_customer_profile,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="campaign_create_unavailable") from None


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: UUID, payload: CampaignUpdate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    try:
        result = await _store(request).update_campaign(
            workspace_id=payload.workspace_id, campaign_id=campaign_id, name=payload.name,
            client_business=payload.client_business, client_offer=payload.client_offer,
            target_customer_profile=payload.target_customer_profile, status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="campaign_update_unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="campaign_not_found")
    return result


@router.get("/campaigns")
async def list_campaigns(request: Request, workspace_id: str = Query(min_length=1, max_length=200),
                         limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=100000)):
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    return {"items": await _store(request).list_campaigns(workspace_id=workspace_id, limit=limit, offset=offset),
            "limit": limit, "offset": offset}


class DraftEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    subject: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1, max_length=10000)

    @field_validator("body")
    @classmethod
    def valid_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("draft_body_invalid")
        return value

    @field_validator("subject")
    @classmethod
    def clean_subject(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None


@router.post("/drafts", status_code=201)
async def create_draft(payload: DraftCreate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    store = _store(request)
    subscriptions = getattr(request.app.state, "subscription_store", None)
    if subscriptions is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")

    ai_enabled = bool(settings.ai_api_key and settings.ai_api_key.strip())
    reservation_id = None
    generated_content = None
    # Template drafts are not AI usage. They remain available when AI is disabled
    # or the AI allowance is exhausted; the database idempotency key prevents replay.
    if ai_enabled:
        try:
            reservation = await subscriptions.reserve_usage(
                workspace_id=payload.workspace_id,
                feature="ai_draft_generations",
                idempotency_key=f"draft-generation:{payload.idempotency_key}",
            )
        except Exception:
            raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
        if not reservation.get("allowed"):
            reason = reservation.get("reason", "entitlement_denied")
            if reason != "quota_exhausted":
                raise HTTPException(status_code=403, detail=reason)
            ai_enabled = False
        else:
            if reservation.get("reason") == "idempotent_replay" or reservation.get("status") == "consumed":
                raise HTTPException(status_code=409, detail="draft_generation_key_already_used")
            reservation_id = reservation["reservation_id"]

    async def finish_reservation(outcome: str) -> None:
        if reservation_id is None:
            return
        try:
            finished = await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome=outcome
            )
        except Exception:
            raise HTTPException(status_code=503, detail="draft_quota_persistence_failed") from None
        if not finished:
            raise HTTPException(status_code=503, detail="draft_quota_persistence_failed")

    if ai_enabled:
        try:
            context = await store.get_draft_generation_context(
                workspace_id=payload.workspace_id,
                campaign_id=payload.campaign_id,
                prospect_id=payload.prospect_id,
                channel=payload.channel,
            )
            if context is None:
                await finish_reservation("released")
                raise HTTPException(status_code=404, detail="campaign_or_prospect_not_found")
            generated_content = await generate_ai_outreach(
                api_key=settings.ai_api_key.strip(),
                base_url=settings.ai_base_url,
                model=settings.ai_model,
                channel=payload.channel,
                call_to_action=payload.call_to_action,
                context=context,
            )
        except AIOutreachUnavailable as exc:
            await finish_reservation("released")
            raise HTTPException(status_code=503, detail=str(exc)) from None
        except ValueError as exc:
            await finish_reservation("released")
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except HTTPException:
            raise
        except Exception:
            await finish_reservation("released")
            raise HTTPException(status_code=503, detail="ai_draft_generation_unavailable") from None

    try:
        draft = await store.create_draft(
            workspace_id=payload.workspace_id, campaign_id=payload.campaign_id,
            prospect_id=payload.prospect_id, actor_id=session["user_id"], channel=payload.channel,
            call_to_action=payload.call_to_action, generated_content=generated_content,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        await finish_reservation("released")
        message = str(exc)
        if message == "idempotency_key_payload_mismatch":
            raise HTTPException(status_code=409, detail=message) from None
        if "WhatsApp" in message or "verified fact" in message or "channel" in message or "prospect_email_required" in message or "prospect_whatsapp_phone_required" in message or "contact_suppressed" in message or "contact_replied" in message:
            raise HTTPException(status_code=422, detail=message) from None
        raise HTTPException(status_code=422, detail="draft_inputs_invalid") from None
    except Exception as exc:
        if type(exc).__name__ == "UniqueViolationError":
            await finish_reservation("released")
            raise HTTPException(status_code=409, detail="pending_draft_already_exists") from None
        try:
            await finish_reservation("consumed")
        finally:
            raise HTTPException(status_code=503, detail="draft_create_unavailable") from None
    if draft is None:
        await finish_reservation("released")
        raise HTTPException(status_code=404, detail="campaign_or_prospect_not_found")
    if reservation_id is not None:
        await finish_reservation("consumed")
    return draft

@router.get("/drafts")
async def list_drafts(request: Request, workspace_id: str = Query(min_length=1, max_length=200),
                      status: str = Query(default="pending_approval"),
                      limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0, le=100000)):
    if status not in {"pending_approval", "approved", "rejected", "all"}:
        raise HTTPException(status_code=422, detail="invalid_draft_status")
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    return {"items": await _store(request).list_drafts(workspace_id=workspace_id, status=status, limit=limit, offset=offset),
            "limit": limit, "offset": offset, "status": status}


@router.post("/drafts/{draft_id}/review")
async def review_draft(draft_id: UUID, payload: DraftReview, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    try:
        draft = await _store(request).review_draft(
            workspace_id=payload.workspace_id, draft_id=draft_id, actor_id=session["user_id"],
            decision=payload.decision, note=payload.note,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="draft_review_unavailable") from None
    if draft is None:
        raise HTTPException(status_code=409, detail="draft_not_pending_or_not_found")
    return draft


@router.patch("/drafts/{draft_id}")
async def edit_draft(draft_id: UUID, payload: DraftEdit, request: Request):
    """Allow workspace members to edit content before approval; never sends the draft."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    try:
        result = await _store(request).update_draft(
            workspace_id=payload.workspace_id, draft_id=draft_id,
            actor_id=session["user_id"], subject=payload.subject, body=payload.body,
        )
    except ValueError as exc:
        reason = str(exc)
        raise HTTPException(status_code=409 if reason == "draft_not_pending" else 422, detail=reason) from None
    except Exception:
        raise HTTPException(status_code=503, detail="draft_edit_unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return result


@router.post("/drafts/{draft_id}/regenerate")
async def regenerate_draft(draft_id: UUID, payload: DraftRegenerate, request: Request):
    """Regenerate a pending draft while retaining approval and usage safeguards."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    store = _store(request)
    subscriptions = getattr(request.app.state, "subscription_store", None)
    if subscriptions is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    try:
        reservation = await subscriptions.reserve_usage(
            workspace_id=payload.workspace_id,
            feature="ai_draft_generations",
            idempotency_key=f"draft-regeneration:{payload.idempotency_key}",
        )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    if not reservation.get("allowed"):
        reason = reservation.get("reason", "entitlement_denied")
        raise HTTPException(status_code=429 if reason == "quota_exhausted" else 403, detail=reason)
    if reservation.get("reason") == "idempotent_replay" or reservation.get("status") == "consumed":
        raise HTTPException(status_code=409, detail="draft_regeneration_key_already_used")
    reservation_id = reservation["reservation_id"]
    try:
        context = await store.get_draft_regeneration_context(
            workspace_id=payload.workspace_id, draft_id=draft_id
        )
        if context is None:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
            )
            raise HTTPException(status_code=404, detail="draft_not_found")
        generated_content = None
        if settings.ai_api_key and settings.ai_api_key.strip():
            generated_content = await generate_ai_outreach(
                api_key=settings.ai_api_key.strip(), base_url=settings.ai_base_url,
                model=settings.ai_model, channel=context["_channel"],
                call_to_action=payload.call_to_action, context=context,
            )
    except HTTPException:
        raise
    except ValueError as exc:
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=409 if str(exc) == "draft_not_pending" else 422, detail=str(exc)) from None
    except AIOutreachUnavailable as exc:
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except Exception:
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=503, detail="draft_regeneration_unavailable") from None

    try:
        updated = await store.regenerate_pending_draft(
            workspace_id=payload.workspace_id, draft_id=draft_id,
            actor_id=session["user_id"], call_to_action=payload.call_to_action,
            generated_content=generated_content,
        )
    except ValueError as exc:
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=409 if str(exc) == "draft_not_pending" else 422, detail=str(exc)) from None
    except Exception:
        # The database commit may have succeeded before the connection failed.
        # Consume quota to prevent a free retry from duplicating an ambiguous regeneration.
        try:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
        finally:
            raise HTTPException(status_code=503, detail="draft_regeneration_outcome_unknown") from None
    if updated is None:
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=404, detail="draft_not_found")
    # As above, a locally generated fallback is not an AI-provider generation.
    quota_outcome = "consumed" if generated_content is not None else "released"
    try:
        finished = await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome=quota_outcome
        )
    except Exception:
        raise HTTPException(status_code=503, detail="draft_quota_persistence_failed") from None
    if not finished:
        raise HTTPException(status_code=503, detail="draft_quota_persistence_failed")
    return updated


@router.get("/drafts/{draft_id}/events")
async def list_draft_events(
    draft_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
):
    """Expose the persisted draft review/edit timeline to workspace viewers."""
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    try:
        events = await _store(request).list_draft_events(
            workspace_id=workspace_id, draft_id=draft_id, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="draft_history_unavailable") from None
    if events is None:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return {"items": events, "draft_id": str(draft_id), "limit": limit}
