"""Authenticated read-only subscription entitlement inspection for workspace dashboards.

This endpoint exposes the trusted server-side decision only. It does not accept
plan claims from clients, reserve quota, or make a paid operation billable.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.auth_routes import _authenticated
from app.core.config import settings

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/entitlements")
async def get_workspace_entitlement(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    feature: str = Query(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.-]*$"),
):
    """Return one feature decision from a verified subscription snapshot."""
    _, _, session = await _authenticated(request)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role="viewer"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")

    subscription_store = getattr(request.app.state, "subscription_store", None)
    if subscription_store is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    try:
        decision = await subscription_store.get_entitlement(
            workspace_id=workspace_id, feature=feature
        )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    return {
        "workspace_id": workspace_id,
        "feature": feature,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "remaining": decision.remaining,
    }



@router.post("/paddle/webhook")
async def paddle_subscription_webhook(request: Request):
    """Verify a Paddle signature, then apply a server-mapped subscription snapshot."""
    import json

    from app.services.paddle_webhook import (
        PaddleWebhookError,
        parse_paddle_subscription_event,
        verify_paddle_signature,
    )

    secret = settings.paddle_webhook_secret
    plans_json = settings.paddle_plans_json
    if not secret or not plans_json:
        raise HTTPException(status_code=503, detail="paddle_webhook_not_configured")
    content_length = request.headers.get("content-length")
    if content_length and (not content_length.isdigit() or int(content_length) > 1_000_000):
        raise HTTPException(status_code=413, detail="webhook_payload_too_large")
    raw_body = await request.body()
    if len(raw_body) > 1_000_000:
        raise HTTPException(status_code=413, detail="webhook_payload_too_large")
    try:
        verify_paddle_signature(raw_body, request.headers.get("paddle-signature"), secret)
    except PaddleWebhookError:
        raise HTTPException(status_code=401, detail="invalid_paddle_signature") from None
    try:
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError("invalid_payload")
        event_type = payload.get("event_type")
        if not isinstance(event_type, str) or not event_type.startswith("subscription."):
            return {"outcome": "ignored"}
        plans = json.loads(plans_json)
        if not isinstance(plans, dict):
            raise ValueError("invalid_plan_configuration")
        event = parse_paddle_subscription_event(payload, plans)
    except (PaddleWebhookError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="invalid_paddle_subscription_event") from None

    store = getattr(request.app.state, "billing_lifecycle_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    try:
        return await store.apply_verified_event(event)
    except ValueError:
        raise HTTPException(status_code=409, detail="billing_event_conflict") from None
    except Exception:
        raise HTTPException(status_code=503, detail="billing_event_processing_unavailable") from None
