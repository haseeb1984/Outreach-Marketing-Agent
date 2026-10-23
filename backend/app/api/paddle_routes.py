"""Paddle Billing checkout and signed subscription lifecycle webhook.

Only server-configured plan IDs are purchasable. Webhook bodies are verified from
raw bytes before any state changes. Never trust browser redirects for paid access.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings
from app.services.billing_lifecycle_store import VerifiedBillingEvent

router = APIRouter(prefix="/api/v1/billing/paddle", tags=["billing"])


class CheckoutRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=200)
    plan_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")


def _plans() -> dict[str, Any]:
    raw = settings.paddle_plans_json
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=503, detail="billing_plan_catalog_invalid") from None
    if not isinstance(value, dict):
        raise HTTPException(status_code=503, detail="billing_plan_catalog_invalid")
    for slug, plan in value.items():
        if (not isinstance(slug, str) or not isinstance(plan, dict)
                or not isinstance(plan.get("price_id"), str)
                or not plan["price_id"].startswith("pri_")
                or not isinstance(plan.get("entitlements"), dict)):
            raise HTTPException(status_code=503, detail="billing_plan_catalog_invalid")
    return value



async def _effective_plans(request: Request, *, include_inactive: bool = False) -> dict[str, Any]:
    """Use the platform-admin catalog once seeded; keep env plans as a bootstrap fallback."""
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        return _plans()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT slug,name,description,price_id,display_price,currency,billing_interval,
                          entitlements,active
                   FROM platform_billing_plans ORDER BY slug"""
            )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_plan_catalog_unavailable") from None
    if not rows:
        return _plans()
    result: dict[str, Any] = {}
    for row in rows:
        item = dict(row)
        if not include_inactive and not item.get("active"):
            continue
        value = item.get("entitlements")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                raise HTTPException(status_code=503, detail="billing_plan_catalog_invalid") from None
        if not isinstance(value, dict) or not isinstance(item.get("price_id"), str) or not item["price_id"].startswith("pri_"):
            raise HTTPException(status_code=503, detail="billing_plan_catalog_invalid")
        item["entitlements"] = value
        result[item["slug"]] = item
    return result


def _api_base() -> str:
    if settings.paddle_environment == "sandbox":
        return "https://sandbox-api.paddle.com"
    if settings.paddle_environment == "production":
        return "https://api.paddle.com"
    raise HTTPException(status_code=503, detail="billing_environment_invalid")


@router.get("/plans")
async def list_public_plans(request: Request):
    """Expose only display-safe, server-configured plans; never return Paddle price IDs or secrets."""
    plans = await _effective_plans(request)
    items = []
    for slug, plan in plans.items():
        name = plan.get("name")
        if not isinstance(name, str) or not name.strip():
            name = slug.replace("-", " ").replace("_", " ").title()
        display_price = plan.get("display_price")
        currency = plan.get("currency")
        interval = plan.get("billing_interval")
        description = plan.get("description")
        items.append({
            "id": slug,
            "name": name[:120],
            "description": description[:500] if isinstance(description, str) else "",
            "display_price": display_price[:80] if isinstance(display_price, str) else None,
            "currency": currency[:8] if isinstance(currency, str) else None,
            "billing_interval": interval[:40] if isinstance(interval, str) else None,
            "checkout_available": bool(settings.paddle_api_key and settings.paddle_webhook_secret) and (settings.paddle_environment != "production" or settings.paddle_live_checkout_enabled),
        })
    return {"items": items, "configured": bool(items)}


@router.post("/checkout")
async def create_checkout(body: CheckoutRequest, request: Request):
    """Create a Paddle-hosted transaction for an authorized workspace owner/admin."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=body.workspace_id, minimum_role="admin"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")

    if settings.paddle_environment == "production" and not settings.paddle_live_checkout_enabled:
        raise HTTPException(status_code=403, detail="paddle_live_checkout_disabled")
    if not settings.paddle_api_key:
        raise HTTPException(status_code=503, detail="paddle_not_configured")
    plan = (await _effective_plans(request)).get(body.plan_id)
    if plan is None:
        raise HTTPException(status_code=422, detail="unknown_billing_plan")

    payload = {
        "items": [{"price_id": plan["price_id"], "quantity": 1}],
        "collection_mode": "automatic",
        "custom_data": {
            "workspace_id": body.workspace_id,
            "plan_id": body.plan_id,
            "billing_integration": "outreach-marketing-agent",
        },
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{_api_base()}/transactions",
                headers={
                    "Authorization": f"Bearer {settings.paddle_api_key}",
                    "Paddle-Version": "1",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code not in (200, 201):
            # Do not return Paddle response bodies, which may include sensitive diagnostics.
            raise HTTPException(status_code=502, detail="paddle_checkout_creation_failed")
        data = response.json().get("data", {})
        checkout_url = data.get("checkout", {}).get("url") if isinstance(data, dict) else None
        if not isinstance(checkout_url, str) or not checkout_url.startswith("https://"):
            raise HTTPException(status_code=502, detail="paddle_checkout_url_unavailable")
        return {"checkout_url": checkout_url, "transaction_id": data.get("id"), "plan_id": body.plan_id}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="paddle_checkout_unavailable") from None


def _verify_signature(raw_body: bytes, header: str | None, secret: str) -> bool:
    if not header or len(header) > 4096:
        return False
    values: dict[str, list[str]] = {}
    for part in header.split(";"):
        key, sep, value = part.strip().partition("=")
        if sep and key and value:
            values.setdefault(key, []).append(value)
    timestamps = values.get("ts", [])
    signatures = values.get("h1", [])
    if len(timestamps) != 1 or not signatures:
        return False
    try:
        timestamp = int(timestamps[0])
    except (TypeError, ValueError):
        return False
    if abs(time.time() - timestamp) > 300:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), timestamps[0].encode("ascii") + b":" + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return any(
        len(sig) == len(expected) and hmac.compare_digest(expected, sig)
        for sig in signatures
    )


def _datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("missing_billing_timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone_required")
    return parsed


@router.post("/webhook")
async def paddle_webhook(request: Request):
    """Verify Paddle signature and apply only recognized subscription snapshots."""
    secret = settings.paddle_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="paddle_webhook_not_configured")
    raw_body = await request.body()
    if len(raw_body) > 1_000_000:
        raise HTTPException(status_code=413, detail="webhook_payload_too_large")
    if not _verify_signature(raw_body, request.headers.get("Paddle-Signature"), secret):
        raise HTTPException(status_code=401, detail="invalid_paddle_signature")
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="invalid_webhook_payload") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_webhook_payload")

    event_type = payload.get("event_type")
    if event_type not in {
        "subscription.created", "subscription.updated", "subscription.canceled",
        "subscription.past_due", "subscription.paused", "subscription.resumed",
        "subscription.activated",
    }:
        # Acknowledge unrelated, correctly signed notifications without granting access.
        return {"received": True, "outcome": "ignored"}
    data = payload.get("data")
    custom_data = data.get("custom_data") if isinstance(data, dict) else None
    workspace_id = custom_data.get("workspace_id") if isinstance(custom_data, dict) else None
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise HTTPException(status_code=422, detail="workspace_mapping_missing")

    plans = await _effective_plans(request, include_inactive=True)
    items = data.get("items")
    price_ids = {
        item.get("price", {}).get("id")
        for item in items if isinstance(item, dict) and isinstance(item.get("price"), dict)
    } if isinstance(items, list) else set()
    matching = [(slug, plan) for slug, plan in plans.items() if plan["price_id"] in price_ids]
    if len(matching) != 1:
        raise HTTPException(status_code=422, detail="subscription_plan_mapping_invalid")
    matched_slug, plan = matching[0]
    declared_plan = custom_data.get("plan_id")
    if not isinstance(declared_plan, str) or declared_plan != matched_slug:
        raise HTTPException(status_code=422, detail="subscription_plan_metadata_mismatch")
    provider_subscription_id = data.get("id")
    provider_event_id = payload.get("event_id")
    if (not isinstance(provider_subscription_id, str) or not provider_subscription_id.strip()
            or not isinstance(provider_event_id, str) or not provider_event_id.strip()):
        raise HTTPException(status_code=422, detail="subscription_event_identity_missing")

    status_map = {
        "active": "active", "trialing": "trialing", "past_due": "past_due",
        "canceled": "cancelled", "paused": "paused", "past_due": "past_due",
        "incomplete": "incomplete", "unpaid": "unpaid",
    }
    status = status_map.get(data.get("status"))
    if event_type == "subscription.canceled":
        status = "cancelled"
    elif event_type == "subscription.paused":
        status = "paused"
    elif event_type in {"subscription.activated", "subscription.resumed"}:
        status = "active"
    if status is None:
        raise HTTPException(status_code=422, detail="subscription_status_unsupported")

    current_period = data.get("current_billing_period")
    try:
        occurred_at = _datetime(payload["occurred_at"])
        if isinstance(current_period, dict):
            period_starts_at = _datetime(current_period["starts_at"])
            period_ends_at = _datetime(current_period["ends_at"])
        elif status in {"cancelled", "paused"}:
            # Paddle omits current_billing_period for canceled/paused subscriptions.
            # Preserve the last known period where possible; status still denies access.
            pool = getattr(request.app.state, "db_pool", None)
            prior = None
            if pool is not None:
                async with pool.acquire() as conn:
                    prior = await conn.fetchrow(
                        """SELECT billing_period_starts_at,billing_period_ends_at
                           FROM workspace_subscriptions
                           WHERE workspace_id=$1 AND provider='paddle'
                             AND provider_subscription_id=$2""",
                        workspace_id, str(data["id"]),
                    )
            if prior is not None:
                period_starts_at = prior["billing_period_starts_at"]
                period_ends_at = prior["billing_period_ends_at"]
            else:
                # A terminal event may arrive before creation; canceled/paused status denies access.
                period_starts_at = occurred_at
                period_ends_at = occurred_at + timedelta(seconds=1)
        else:
            raise ValueError("missing_billing_period")
        event = VerifiedBillingEvent(
            provider="paddle",
            event_id=provider_event_id,
            workspace_id=workspace_id,
            provider_customer_id=data.get("customer_id"),
            provider_subscription_id=provider_subscription_id,
            plan_slug=matched_slug,
            event_created_at=occurred_at,
            subscription_status=status,
            period_starts_at=period_starts_at,
            period_ends_at=period_ends_at,
            entitlements=plan["entitlements"],
        )
        store = getattr(request.app.state, "billing_lifecycle_store", None)
        if store is None:
            raise HTTPException(status_code=503, detail="billing_service_not_configured")
        outcome = await store.apply_verified_event(event)
    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="subscription_event_invalid") from None
    except Exception:
        raise HTTPException(status_code=503, detail="billing_event_processing_unavailable") from None
    return {"received": True, **outcome}
