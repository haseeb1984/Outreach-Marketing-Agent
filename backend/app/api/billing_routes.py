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



from pydantic import BaseModel, ConfigDict, Field
from app.api.auth_routes import _check_csrf
from app.services.paddle_api import PaddleAPIError, create_checkout_transaction, create_customer_portal_session


class PaddleCheckoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    price_id: str = Field(min_length=5, max_length=100, pattern=r"^pri_[A-Za-z0-9_-]+$")


def _paddle_plan_config() -> dict:
    import json
    if not settings.paddle_plans_json:
        raise HTTPException(status_code=503, detail="paddle_plans_not_configured")
    try:
        plans = json.loads(settings.paddle_plans_json)
    except (TypeError, ValueError):
        raise HTTPException(status_code=503, detail="paddle_plans_not_configured") from None
    if not isinstance(plans, dict):
        raise HTTPException(status_code=503, detail="paddle_plans_not_configured")
    return plans


def _require_paddle_api() -> tuple[str, str, bool]:
    if not settings.paddle_api_key:
        raise HTTPException(status_code=503, detail="paddle_api_not_configured")
    return settings.paddle_api_key, settings.paddle_environment, settings.paddle_live_checkout_enabled


@router.post("/paddle/checkout")
async def start_paddle_checkout(payload: PaddleCheckoutInput, request: Request):
    """Create a hosted checkout for a workspace owner using an allow-listed price."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=payload.workspace_id, minimum_role="owner"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    plan = _paddle_plan_config().get(payload.price_id)
    if not isinstance(plan, dict) or not isinstance(plan.get("slug"), str) or not isinstance(plan.get("entitlements"), dict):
        raise HTTPException(status_code=422, detail="paddle_price_not_available")
    api_key, environment, live_enabled = _require_paddle_api()
    try:
        transaction = await create_checkout_transaction(
            api_key=api_key,
            environment=environment,
            live_enabled=live_enabled,
            price_id=payload.price_id,
            workspace_id=payload.workspace_id,
            plan_slug=plan["slug"],
        )
    except PaddleAPIError as exc:
        code = str(exc)
        if code == "live_checkout_disabled":
            raise HTTPException(status_code=503, detail="paddle_live_checkout_disabled") from None
        raise HTTPException(status_code=502, detail="paddle_checkout_unavailable") from None
    return {"transaction_id": transaction["transaction_id"], "checkout_url": transaction["checkout_url"], "plan_slug": plan["slug"]}


@router.post("/paddle/portal")
async def open_paddle_customer_portal(request: Request, workspace_id: str = Query(min_length=1, max_length=200)):
    """Create a portal session for the Paddle customer mapped to an authorized workspace."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role="owner"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    try:
        async with pool.acquire() as conn:
            customer_id = await conn.fetchval(
                "SELECT provider_customer_id FROM workspace_subscriptions WHERE workspace_id=$1 AND provider='paddle'",
                workspace_id,
            )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    if not customer_id:
        raise HTTPException(status_code=404, detail="paddle_customer_not_found")
    api_key, environment, live_enabled = _require_paddle_api()
    try:
        portal_url = await create_customer_portal_session(
            api_key=api_key,
            environment=environment,
            live_enabled=live_enabled,
            customer_id=customer_id,
        )
    except PaddleAPIError:
        raise HTTPException(status_code=502, detail="paddle_portal_unavailable") from None
    return {"portal_url": portal_url}
