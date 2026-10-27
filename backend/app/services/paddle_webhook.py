"""Paddle webhook signature verification and trusted subscription event mapping.

Only signed provider events are accepted. Entitlements come from server configuration,
never from Paddle custom_data or browser-supplied plan claims.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
from typing import Any, Mapping


_MAX_CLOCK_SKEW_SECONDS = 300
_PLAN_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,79}$")
_SUPPORTED_STATUSES = {
    "active": "active",
    "trialing": "trialing",
    "past_due": "past_due",
    "paused": "paused",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "incomplete": "incomplete",
    "unpaid": "unpaid",
}
_SUBSCRIPTION_EVENTS = {
    "subscription.created",
    "subscription.updated",
    "subscription.activated",
    "subscription.canceled",
    "subscription.paused",
    "subscription.resumed",
    "subscription.past_due",
}


class PaddleWebhookError(ValueError):
    """A webhook cannot safely be verified or mapped to a subscription."""


def verify_paddle_signature(
    raw_body: bytes,
    signature_header: str | None,
    secret: str,
    *,
    now_epoch: int | None = None,
    tolerance_seconds: int = _MAX_CLOCK_SKEW_SECONDS,
) -> None:
    """Validate Paddle's ts/h1 HMAC signature with constant-time comparison."""
    if not isinstance(raw_body, bytes) or not raw_body:
        raise PaddleWebhookError("empty_webhook_body")
    if not isinstance(secret, str) or not secret.strip():
        raise PaddleWebhookError("webhook_secret_not_configured")
    if not isinstance(signature_header, str) or len(signature_header) > 2048:
        raise PaddleWebhookError("invalid_webhook_signature")
    fields: dict[str, list[str]] = {}
    for part in signature_header.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key in {"ts", "h1"}:
            fields.setdefault(key, []).append(value)
    timestamps = fields.get("ts", [])
    signatures = fields.get("h1", [])
    if len(timestamps) != 1 or not timestamps[0].isdigit() or not signatures:
        raise PaddleWebhookError("invalid_webhook_signature")
    timestamp = int(timestamps[0])
    current = int(datetime.now(timezone.utc).timestamp()) if now_epoch is None else int(now_epoch)
    if abs(current - timestamp) > tolerance_seconds:
        raise PaddleWebhookError("webhook_timestamp_out_of_range")
    signed_payload = str(timestamp).encode("ascii") + b":" + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(
        len(candidate) == 64 and hmac.compare_digest(candidate.lower(), expected)
        for candidate in signatures
    ):
        raise PaddleWebhookError("invalid_webhook_signature")


def parse_paddle_subscription_event(
    payload: Mapping[str, Any],
    plan_config: Mapping[str, Any],
):
    """Map one signed Paddle subscription snapshot to a provider-neutral event."""
    from app.services.billing_lifecycle_store import VerifiedBillingEvent

    event_type = payload.get("event_type")
    if event_type not in _SUBSCRIPTION_EVENTS:
        raise PaddleWebhookError("unsupported_subscription_event")
    event_id = payload.get("event_id")
    data = payload.get("data")
    occurred_at = _parse_datetime(payload.get("occurred_at"), "occurred_at")
    if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 300:
        raise PaddleWebhookError("invalid_event_id")
    if not isinstance(data, Mapping):
        raise PaddleWebhookError("invalid_subscription_data")
    subscription_id = data.get("id")
    customer_id = data.get("customer_id")
    custom_data = data.get("custom_data")
    workspace_id = custom_data.get("workspace_id") if isinstance(custom_data, Mapping) else None
    if not isinstance(subscription_id, str) or not subscription_id.strip():
        raise PaddleWebhookError("invalid_subscription_id")
    if not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200:
        raise PaddleWebhookError("workspace_mapping_missing")

    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise PaddleWebhookError("subscription_price_missing")
    price_ids = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise PaddleWebhookError("invalid_subscription_items")
        price = item.get("price")
        price_id = price.get("id") if isinstance(price, Mapping) else item.get("price_id")
        if not isinstance(price_id, str) or not price_id.strip():
            raise PaddleWebhookError("subscription_price_missing")
        price_ids.add(price_id)
    if len(price_ids) != 1:
        raise PaddleWebhookError("multiple_subscription_plans_unsupported")
    price_id = next(iter(price_ids))
    configured = plan_config.get(price_id)
    if not isinstance(configured, Mapping):
        raise PaddleWebhookError("unknown_paddle_price")
    plan_slug = configured.get("slug")
    entitlements = configured.get("entitlements")
    if not isinstance(plan_slug, str) or not _PLAN_SLUG.fullmatch(plan_slug):
        raise PaddleWebhookError("invalid_configured_plan")
    if not isinstance(entitlements, Mapping):
        raise PaddleWebhookError("invalid_configured_entitlements")
    try:
        json.dumps(dict(entitlements), allow_nan=False)
    except (TypeError, ValueError):
        raise PaddleWebhookError("invalid_configured_entitlements") from None

    raw_status = data.get("status")
    status = _SUPPORTED_STATUSES.get(raw_status) if isinstance(raw_status, str) else None
    if status is None:
        raise PaddleWebhookError("unsupported_subscription_status")
    period = data.get("current_billing_period")
    if isinstance(period, Mapping):
        starts_at = _parse_datetime(period.get("starts_at"), "period_start")
        ends_at = _parse_datetime(period.get("ends_at"), "period_end")
    elif status == "cancelled":
        # A cancellation snapshot without a current period must revoke access promptly.
        starts_at = occurred_at
        ends_at = occurred_at + timedelta(seconds=1)
    else:
        raise PaddleWebhookError("subscription_period_missing")
    if ends_at <= starts_at:
        raise PaddleWebhookError("invalid_billing_period")
    if customer_id is not None and (not isinstance(customer_id, str) or len(customer_id) > 300):
        raise PaddleWebhookError("invalid_customer_id")

    return VerifiedBillingEvent(
        provider="paddle",
        event_id=event_id,
        workspace_id=workspace_id,
        provider_customer_id=customer_id,
        provider_subscription_id=subscription_id,
        plan_slug=plan_slug,
        event_created_at=occurred_at,
        subscription_status=status,
        period_starts_at=starts_at,
        period_ends_at=ends_at,
        entitlements=dict(entitlements),
    )


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PaddleWebhookError(f"invalid_{field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PaddleWebhookError(f"invalid_{field}") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaddleWebhookError(f"invalid_{field}")
    return parsed.astimezone(timezone.utc)
