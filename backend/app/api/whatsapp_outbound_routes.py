"""Approval- and quota-gated WhatsApp queue. No endpoint here dispatches messages."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth_routes import _authenticated, _check_csrf
from app.services.whatsapp_outbound_store import WhatsAppOutboundStore
from app.services.whatsapp_send_policy import WhatsAppSendPolicy

router = APIRouter(prefix="/api/v1/integrations/whatsapp/outbound", tags=["WhatsApp outbound queue"])


class QueueWhatsAppDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    account_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    template_name: str | None = Field(default=None, min_length=1, max_length=512)
    language_code: str | None = Field(default=None, min_length=2, max_length=32)


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="whatsapp_outbound_queue_not_configured")
    return pool


async def _authorize(request: Request, workspace_id: str, session: dict, role: str) -> None:
    auth = getattr(request.app.state, "auth_store", None)
    if auth is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")


@router.post("/drafts/{draft_id}/queue", status_code=202)
async def queue_whatsapp_draft(
    draft_id: UUID, payload: QueueWhatsAppDraft, request: Request,
) -> dict:
    """Check consent/template/window and quota, then queue for future reviewed dispatch.

    This endpoint never sends a WhatsApp message. Queue rows stay queued until a
    separately approved worker exists; live sending is deliberately not enabled.
    """
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, session, "admin")
    pool = _pool(request)
    subscriptions = getattr(request.app.state, "subscription_store", None)
    if subscriptions is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")

    try:
        decision = await WhatsAppSendPolicy(pool).evaluate(
            workspace_id=payload.workspace_id,
            account_id=payload.account_id,
            prospect_id=await _draft_prospect_id(pool, payload.workspace_id, draft_id),
            draft_id=draft_id,
            template_name=payload.template_name,
            language_code=payload.language_code,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="workspace_draft_not_found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_policy_unavailable") from None
    if not decision.get("allowed"):
        reason = str(decision.get("reason", "whatsapp_policy_denied"))
        raise HTTPException(status_code=403, detail=reason)

    # Replay an already-created queue row before touching quota. This makes a
    # client retry after a lost HTTP response safe and avoids double reservations.
    try:
        existing = await WhatsAppOutboundStore(pool).find_by_idempotency_key(
            workspace_id=payload.workspace_id,
            idempotency_key=payload.idempotency_key,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_queue_lookup_unavailable") from None
    if existing is not None:
        if existing["account_id"] != str(payload.account_id) or existing["draft_id"] != str(draft_id):
            raise HTTPException(status_code=409, detail="whatsapp_idempotency_conflict")
        return {
            **existing,
            "policy_reason": decision["reason"],
            "requires_approved_template": decision["requires_approved_template"],
            "dispatch_enabled": False,
            "notice": "Existing queue record returned. No WhatsApp message was sent; outbound dispatch remains disabled.",
        }

    reservation_key = "whatsapp-send:" + payload.idempotency_key
    try:
        reservation = await subscriptions.reserve_usage(
            workspace_id=payload.workspace_id,
            feature="whatsapp_sends",
            idempotency_key=reservation_key,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    if not reservation.get("allowed"):
        reason = reservation.get("reason", "entitlement_denied")
        raise HTTPException(status_code=429 if reason == "quota_exhausted" else 403, detail=reason)
    if reservation.get("status") == "consumed":
        raise HTTPException(status_code=409, detail="whatsapp_queue_key_already_used")
    # An existing reserved key may be an interrupted request that crashed after
    # quota reservation but before queue insertion. Reuse it to complete the queue.

    try:
        result = await WhatsAppOutboundStore(pool).enqueue(
            workspace_id=payload.workspace_id,
            account_id=payload.account_id,
            draft_id=draft_id,
            actor_id=session["user_id"],
            idempotency_key=payload.idempotency_key,
            usage_reservation_id=reservation["reservation_id"],
        )
        if result.get("replayed") and (
            result.get("usage_reservation_id") != reservation.get("reservation_id")
        ):
            # Only release a separate, newly-created reservation. Never release the
            # reservation that the already-existing queue row depends on.
            if reservation.get("reason") == "reserved":
                await subscriptions.finish_reservation(
                    workspace_id=payload.workspace_id,
                    reservation_id=reservation["reservation_id"],
                    outcome="released",
                )
    except HTTPException:
        raise
    except LookupError as exc:
        if reservation.get("reason") == "reserved":
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id,
                reservation_id=reservation["reservation_id"],
                outcome="released",
            )
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        if reservation.get("reason") == "reserved":
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id,
                reservation_id=reservation["reservation_id"],
                outcome="released",
            )
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception:
        if reservation.get("reason") == "reserved":
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id,
                reservation_id=reservation["reservation_id"],
                outcome="released",
            )
        raise HTTPException(status_code=503, detail="whatsapp_queue_unavailable") from None

    return {
        **result,
        "policy_reason": decision["reason"],
        "requires_approved_template": decision["requires_approved_template"],
        "dispatch_enabled": False,
        "notice": "Queued only. No WhatsApp message was sent; outbound dispatch remains disabled.",
    }


async def _draft_prospect_id(pool, workspace_id: str, draft_id: UUID) -> UUID:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT prospect_id FROM outreach_drafts WHERE id=$1 AND workspace_id=$2",
            draft_id, workspace_id,
        )
    if row is None:
        raise LookupError("workspace_draft_not_found")
    return row["prospect_id"]


@router.get("")
async def list_whatsapp_outbound_queue(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
) -> dict:
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, session, "viewer")
    try:
        items = await WhatsAppOutboundStore(_pool(request)).list(
            workspace_id=workspace_id, limit=limit, offset=offset,
        )
        return {
            "items": items, "limit": limit, "offset": offset,
            "dispatch_enabled": False,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_queue_list_unavailable") from None
