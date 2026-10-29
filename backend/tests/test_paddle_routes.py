from __future__ import annotations

import hashlib
import hmac
import json
import time

from app.api.paddle_routes import _verify_signature


def _signed(body: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(
        secret.encode(), str(ts).encode("ascii") + b":" + body, hashlib.sha256
    ).hexdigest()
    return f"ts={ts};h1={digest}"


def test_paddle_signature_verifies_raw_body():
    body = json.dumps({"event_type": "subscription.updated"}).encode()
    assert _verify_signature(body, _signed(body, "test-webhook-secret"), "test-webhook-secret")


def test_paddle_signature_rejects_modified_body():
    body = b'{"event_type":"subscription.updated"}'
    signature = _signed(body, "test-webhook-secret")
    assert not _verify_signature(body + b" ", signature, "test-webhook-secret")


def test_paddle_signature_rejects_wrong_secret():
    body = b'{"event_type":"subscription.updated"}'
    assert not _verify_signature(body, _signed(body, "right-secret"), "wrong-secret")


def test_paddle_signature_rejects_expired_timestamp():
    body = b'{"event_type":"subscription.updated"}'
    old_timestamp = int(time.time()) - 600
    assert not _verify_signature(
        body, _signed(body, "test-webhook-secret", old_timestamp), "test-webhook-secret"
    )


def test_paddle_signature_rejects_malformed_header():
    assert not _verify_signature(b"{}", "not-a-signature", "test-webhook-secret")



def test_checkout_url_requires_exact_paddle_host_for_environment(monkeypatch):
    from app.api import paddle_routes

    monkeypatch.setattr(paddle_routes.settings, "paddle_environment", "sandbox")
    assert paddle_routes._trusted_checkout_url("https://sandbox-checkout.paddle.com/checkout/abc")
    assert not paddle_routes._trusted_checkout_url("https://checkout.paddle.com/checkout/abc")
    assert not paddle_routes._trusted_checkout_url("https://attacker.example/checkout/abc")
    assert not paddle_routes._trusted_checkout_url("https://sandbox-checkout.paddle.com.attacker.example/checkout")
    assert not paddle_routes._trusted_checkout_url("https://user@sandbox-checkout.paddle.com/checkout")
    assert not paddle_routes._trusted_checkout_url("http://sandbox-checkout.paddle.com/checkout")
    assert not paddle_routes._trusted_checkout_url("https://sandbox-checkout.paddle.com:444/checkout")
    assert not paddle_routes._trusted_checkout_url(None)


def test_checkout_url_requires_production_host(monkeypatch):
    from app.api import paddle_routes

    monkeypatch.setattr(paddle_routes.settings, "paddle_environment", "production")
    assert paddle_routes._trusted_checkout_url("https://checkout.paddle.com/checkout/abc")
    assert not paddle_routes._trusted_checkout_url("https://sandbox-checkout.paddle.com/checkout/abc")
    monkeypatch.setattr(paddle_routes.settings, "paddle_environment", "invalid")
    assert not paddle_routes._trusted_checkout_url("https://checkout.paddle.com/checkout/abc")



def test_customer_portal_url_requires_exact_paddle_host_for_environment(monkeypatch):
    from app.api import paddle_routes

    monkeypatch.setattr(paddle_routes.settings, "paddle_environment", "sandbox")
    assert paddle_routes._trusted_portal_url("https://customer-portal.sandbox.paddle.com/session/abc")
    assert not paddle_routes._trusted_portal_url("https://customer-portal.paddle.com/session/abc")
    assert not paddle_routes._trusted_portal_url("https://customer-portal.sandbox.paddle.com.attacker.example/session")
    assert not paddle_routes._trusted_portal_url("http://customer-portal.sandbox.paddle.com/session")
    monkeypatch.setattr(paddle_routes.settings, "paddle_environment", "production")
    assert paddle_routes._trusted_portal_url("https://customer-portal.paddle.com/session/abc")
    assert not paddle_routes._trusted_portal_url("https://customer-portal.sandbox.paddle.com/session/abc")



def test_paddle_webhook_rejects_requests_when_secret_is_missing(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", "")
    with TestClient(app) as client:
        response = client.post("/api/v1/billing/paddle/webhook", content=b"{}")
    assert response.status_code == 503
    assert response.json()["detail"] == "paddle_webhook_not_configured"


def test_paddle_webhook_rejects_invalid_signature_before_parsing_payload(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", "integration-secret")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/billing/paddle/webhook",
            headers={"Paddle-Signature": "ts=1;h1=invalid"},
            content=b"not-json",
        )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_paddle_signature"


def test_paddle_webhook_rejects_signed_malformed_json(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    secret = "integration-secret"
    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", secret)
    body = b"{invalid-json"
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/billing/paddle/webhook",
            headers={"Paddle-Signature": _signed(body, secret)},
            content=body,
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_webhook_payload"


def test_paddle_webhook_ignores_unrelated_signed_event_without_billing_store(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    secret = "integration-secret"
    body = json.dumps({"event_id": "evt_unrelated", "event_type": "transaction.completed"}).encode()
    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", secret)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/billing/paddle/webhook",
            headers={"Paddle-Signature": _signed(body, secret)},
            content=body,
        )
    assert response.status_code == 200
    assert response.json() == {"received": True, "outcome": "ignored"}


def test_paddle_public_plans_never_expose_provider_price_ids_or_entitlements(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    monkeypatch.setattr(
        paddle_routes.settings,
        "paddle_plans_json",
        json.dumps({
            "starter": {
                "name": "Starter",
                "description": "For small teams",
                "price_id": "pri_private_provider_id",
                "display_price": "$19",
                "currency": "USD",
                "billing_interval": "month",
                "entitlements": {"email_outreach": {"enabled": True, "monthly_limit": 100}},
            }
        }),
    )
    monkeypatch.setattr(paddle_routes.settings, "paddle_api_key", "")
    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", "")
    with TestClient(app) as client:
        response = client.get("/api/v1/billing/paddle/plans")
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["items"][0]["id"] == "starter"
    assert payload["items"][0]["checkout_available"] is False
    assert "price_id" not in response.text
    assert "pri_private_provider_id" not in response.text
    assert "entitlements" not in response.text


def test_paddle_sandbox_plan_catalog_maps_owner_supplied_price_ids(monkeypatch):
    from app.api import paddle_routes

    monkeypatch.setattr(
        paddle_routes.settings,
        "paddle_plans_json",
        json.dumps({
            "starter": {"price_id": "pri_01m61xstp0gy07re6ynykhdcgb", "entitlements": {}},
            "growth": {"price_id": "pri_01m61y1n4enqgf0qbtbm67tkx2", "entitlements": {}},
            "agency": {"price_id": "pri_01m61y66jhcs5qf0cf9n20a3xf", "entitlements": {}},
        }),
    )
    plans = paddle_routes._plans()
    assert plans["starter"]["price_id"] == "pri_01m61xstp0gy07re6ynykhdcgb"
    assert plans["growth"]["price_id"] == "pri_01m61y1n4enqgf0qbtbm67tkx2"
    assert plans["agency"]["price_id"] == "pri_01m61y66jhcs5qf0cf9n20a3xf"
    assert len({plan["price_id"] for plan in plans.values()}) == 3


def test_checkout_rejects_plan_with_empty_entitlements_before_provider_call(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    monkeypatch.setattr(paddle_routes.settings, "paddle_environment", "sandbox")
    monkeypatch.setattr(paddle_routes.settings, "paddle_api_key", "sandbox-key")
    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", "sandbox-secret")
    monkeypatch.setattr(paddle_routes.settings, "paddle_plans_json", json.dumps({
        "starter": {"price_id": "pri_test_starter", "entitlements": {}}
    }))

    class AuthStore:
        async def authorize_workspace(self, **kwargs):
            return True

    async def fake_authenticated(request):
        return AuthStore(), None, {"user_id": "user-1"}

    monkeypatch.setattr(paddle_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(paddle_routes, "_check_csrf", lambda request, session: None)
    with TestClient(app) as client:
        app.state.auth_store = AuthStore()
        response = client.post(
            "/api/v1/billing/paddle/checkout",
            json={"workspace_id": "workspace-1", "plan_id": "starter"},
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "billing_plan_entitlements_not_configured"
