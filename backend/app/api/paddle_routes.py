"""Paddle Billing checkout and signed subscription lifecycle webhook.

Only server-configured plan IDs are purchasable. Webhook bodies are verified from
raw bytes before any state changes. Never trust browser redirects for paid access.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlsplit
from datetime import datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings
from app.services.billing_lifecycle_store import VerifiedBillingEvent

router = APIRouter(prefix="/api/v1/billing/paddle", tags=["billing"])


REQUIRED_ENTITLEMENT_KEYS = frozenset({
    "ai_draft_generations", "email_sends", "website_audits", "whatsapp_sends", "prospect_research",
})


def _valid_entitlements(value: Any, *, require_all_features: bool = True) -> bool:
    """Validate server-owned quota policies; booleans are not integer quotas."""
    if not isinstance(value, dict) or not value:
        return False
    if require_all_features and not REQUIRED_ENTITLEMENT_KEYS.issubset(value):
        return False
    for key, policy in value.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(policy, dict):
            return False
        if not isinstance(policy.get("enabled"), bool) or "monthly_limit" not in policy:
            return False
        limit = policy["monthly_limit"]
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit < 0
        ):
            return False
    return True


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
    seen_price_ids: set[str] = set()
    for slug, plan in value.items():
        price_id = plan.get("price_id") if isinstance(plan, dict) else None
        if (not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", slug)
                or not isinstance(plan, dict)
                or not isinstance(price_id, str)
                or not re.fullmatch(r"pri_[A-Za-z0-9_-]+", price_id)
                or price_id in seen_price_ids
                or not isinstance(plan.get("entitlements"), dict)
                or (plan.get("entitlements") and not _valid_entitlements(plan["entitlements"]))):
            raise HTTPException(status_code=503, detail="billing_plan_catalog_invalid")
        seen_price_ids.add(price_id)
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
    seen_price_ids: set[str] = set()
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
        price_id = item.get("price_id")
        if (not isinstance(value, dict)
                or (value and not _valid_entitlements(value))
                or not isinstance(price_id, str)
                or not re.fullmatch(r"pri_[A-Za-z0-9_-]+", price_id)
                or price_id in seen_price_ids):
            # A provider price must map to exactly one plan, otherwise a signed
            # subscription event cannot be safely resolved to a single entitlement set.
            raise HTTPException(status_code=503, detail="billing_plan_catalog_invalid")
        seen_price_ids.add(price_id)
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
            "checkout_available": (
                _valid_entitlements(plan.get("entitlements"))
                and bool(settings.paddle_api_key and settings.paddle_webhook_secret)
                and (settings.paddle_environment != "production" or settings.paddle_live_checkout_enabled)
            ),
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

    if not _valid_entitlements(plan.get("entitlements")):
        raise HTTPException(status_code=503, detail="billing_plan_entitlements_not_configured")

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
        if not _trusted_checkout_url(checkout_url):
            raise HTTPException(status_code=502, detail="paddle_checkout_url_unavailable")
        return {"checkout_url": checkout_url, "transaction_id": data.get("id"), "plan_id": body.plan_id}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="paddle_checkout_unavailable") from None


def _trusted_checkout_url(value: Any) -> bool:
    """Only redirect users to the Paddle checkout host for the configured environment."""
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    expected_host = (
        "sandbox-checkout.paddle.com"
        if settings.paddle_environment == "sandbox"
        else "checkout.paddle.com"
        if settings.paddle_environment == "production"
        else None
    )
    return bool(
        expected_host
        and parsed.scheme == "https"
        and hostname == expected_host
        and parsed.username is None
        and parsed.password is None
        and port is None
        and parsed.path.startswith("/")
    )


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


def _subscription_price_ids(items: Any) -> set[str]:
    """Accept only the single configured base-plan item this product currently supports.

    Silently selecting a known price from a multi-item subscription could grant a
    base plan while ignoring unknown add-ons or conflicting quantities.
    """
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise ValueError("subscription_items_unsupported")
    item = items[0]
    price = item.get("price")
    price_id = price.get("id") if isinstance(price, dict) else None
    quantity = item.get("quantity")
    if (not isinstance(price_id, str) or not re.fullmatch(r"pri_[A-Za-z0-9_-]+", price_id)
            or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity != 1):
        raise ValueError("subscription_items_unsupported")
    return {price_id}


def _resolve_subscription_plan(custom_data: Any, price_ids: set[Any], plans: dict[str, Any]) -> tuple[str, Any]:
    """Require provider price and our signed custom metadata to identify one same plan."""
    if not isinstance(custom_data, dict):
        raise ValueError("workspace_mapping_missing")
    declared_plan = custom_data.get("plan_id")
    if not isinstance(declared_plan, str) or not declared_plan:
        raise ValueError("subscription_plan_metadata_missing")
    matching = [(slug, plan) for slug, plan in plans.items()
                if isinstance(plan, dict) and plan.get("price_id") in price_ids]
    if len(matching) != 1:
        raise ValueError("subscription_plan_mapping_invalid")
    matched_slug, plan = matching[0]
    if declared_plan != matched_slug:
        raise ValueError("subscription_plan_metadata_mismatch")
    return matched_slug, plan


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
    # Stream with a hard cap instead of request.body(), which buffers the entire
    # attacker-controlled payload before the size check can run.
    max_payload_bytes = 1_000_000
    chunks: list[bytes] = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > max_payload_bytes:
            raise HTTPException(status_code=413, detail="webhook_payload_too_large")
        chunks.append(chunk)
    raw_body = b"".join(chunks)
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
    try:
        price_ids = _subscription_price_ids(items)
        matched_slug, plan = _resolve_subscription_plan(custom_data, price_ids, plans)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if not _valid_entitlements(plan.get("entitlements")):
        raise HTTPException(status_code=422, detail="subscription_plan_entitlements_invalid")
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



@router.post("/portal")
async def create_customer_portal(request: Request, workspace_id: str):
    """Open a Paddle customer portal only for an authorized workspace owner/admin."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role="admin"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    if not settings.paddle_api_key:
        raise HTTPException(status_code=503, detail="paddle_not_configured")
    try:
        async with pool.acquire() as conn:
            customer_id = await conn.fetchval(
                """SELECT provider_customer_id FROM workspace_subscriptions
                   WHERE workspace_id=$1 AND provider='paddle' AND provider_customer_id IS NOT NULL""",
                workspace_id,
            )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    if not _valid_customer_id(customer_id):
        raise HTTPException(status_code=404, detail="paddle_customer_not_found")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{_api_base()}/customers/{customer_id}/portal-sessions",
                headers={
                    "Authorization": f"Bearer {settings.paddle_api_key}",
                    "Paddle-Version": "1",
                    "Content-Type": "application/json",
                },
                json={},
            )
        if response.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail="paddle_portal_creation_failed")
        data = response.json().get("data", {})
        urls = data.get("urls", {}) if isinstance(data, dict) else {}
        general = urls.get("general", {}) if isinstance(urls, dict) else {}
        portal_url = general.get("overview") if isinstance(general, dict) else None
        if not _trusted_portal_url(portal_url):
            raise HTTPException(status_code=502, detail="paddle_portal_url_unavailable")
        return {"portal_url": portal_url}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="paddle_portal_unavailable") from None


def _valid_customer_id(value: Any) -> bool:
    """Accept only a Paddle customer identifier before interpolating it into an API path."""
    return isinstance(value, str) and len(value) <= 100 and re.fullmatch(r"ctm_[A-Za-z0-9]+", value) is not None


def _trusted_portal_url(value: Any) -> bool:
    """Allow only the documented Paddle customer-portal host for the active environment."""
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    expected_host = (
        "customer-portal.sandbox.paddle.com"
        if settings.paddle_environment == "sandbox"
        else "customer-portal.paddle.com"
        if settings.paddle_environment == "production"
        else None
    )
    return bool(
        expected_host
        and parsed.scheme == "https"
        and hostname == expected_host
        and parsed.username is None
        and parsed.password is None
        and port is None
        and parsed.path.startswith("/")
    )
