import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.services.paddle_webhook import (
    PaddleWebhookError,
    parse_paddle_subscription_event,
    verify_paddle_signature,
)


NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
SECRET = "test-webhook-secret"
PLANS = {
    "pri_starter": {
        "slug": "starter",
        "entitlements": {
            "website_audits": {"enabled": True, "monthly_limit": 10},
            "email_outreach": {"enabled": True, "monthly_limit": 100},
        },
    }
}


def _signature(body: bytes, ts: int) -> str:
    signed = str(ts).encode() + b":" + body
    digest = hmac.new(SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return f"ts={ts};h1={digest}"


def _payload(**overrides):
    value = {
        "event_id": "evt_123456789",
        "event_type": "subscription.updated",
        "occurred_at": NOW.isoformat(),
        "data": {
            "id": "sub_123",
            "customer_id": "ctm_123",
            "status": "active",
            "custom_data": {"workspace_id": "workspace-123"},
            "items": [{"price": {"id": "pri_starter"}}],
            "current_billing_period": {
                "starts_at": (NOW - timedelta(days=1)).isoformat(),
                "ends_at": (NOW + timedelta(days=29)).isoformat(),
            },
        },
    }
    value.update(overrides)
    return value


def test_valid_signature_accepts_current_signed_body():
    body = b'{"event_id":"evt_1"}'
    verify_paddle_signature(body, _signature(body, int(NOW.timestamp())), SECRET, now_epoch=int(NOW.timestamp()))


@pytest.mark.parametrize("header", [None, "", "ts=abc;h1=bad", "ts=1793188800;h1=" + "0" * 64])
def test_invalid_signature_is_rejected(header):
    with pytest.raises(PaddleWebhookError):
        verify_paddle_signature(b'{"ok":true}', header, SECRET, now_epoch=int(NOW.timestamp()))


def test_signature_timestamp_replay_window_is_enforced():
    body = b'{"event_id":"evt_1"}'
    old = int((NOW - timedelta(minutes=10)).timestamp())
    with pytest.raises(PaddleWebhookError, match="timestamp_out_of_range"):
        verify_paddle_signature(body, _signature(body, old), SECRET, now_epoch=int(NOW.timestamp()))


def test_signed_payload_maps_server_configured_plan_and_entitlements():
    event = parse_paddle_subscription_event(_payload(), PLANS)
    assert event.provider == "paddle"
    assert event.workspace_id == "workspace-123"
    assert event.provider_subscription_id == "sub_123"
    assert event.plan_slug == "starter"
    assert event.entitlements["website_audits"]["monthly_limit"] == 10
    assert event.subscription_status == "active"


def test_browser_or_payload_cannot_invent_entitlements():
    payload = _payload()
    payload["data"]["custom_data"]["entitlements"] = {"admin": True}
    event = parse_paddle_subscription_event(payload, PLANS)
    assert "admin" not in event.entitlements


def test_unknown_price_fails_closed():
    payload = _payload()
    payload["data"]["items"][0]["price"]["id"] = "pri_unknown"
    with pytest.raises(PaddleWebhookError, match="unknown_paddle_price"):
        parse_paddle_subscription_event(payload, PLANS)


def test_workspace_mapping_is_required():
    payload = _payload()
    payload["data"]["custom_data"] = {}
    with pytest.raises(PaddleWebhookError, match="workspace_mapping_missing"):
        parse_paddle_subscription_event(payload, PLANS)


def test_mixed_price_subscription_is_rejected():
    payload = _payload()
    payload["data"]["items"].append({"price": {"id": "pri_other"}})
    with pytest.raises(PaddleWebhookError, match="multiple_subscription_plans"):
        parse_paddle_subscription_event(payload, PLANS)


def test_cancelled_event_without_period_expires_access_immediately():
    payload = _payload(event_type="subscription.canceled")
    payload["data"]["status"] = "canceled"
    payload["data"]["current_billing_period"] = None
    event = parse_paddle_subscription_event(payload, PLANS)
    assert event.subscription_status == "cancelled"
    assert event.period_ends_at - event.period_starts_at == timedelta(seconds=1)
