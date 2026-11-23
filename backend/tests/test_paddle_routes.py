from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime

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
    body = json.dumps({"event_id": "evt_unrelated", "event_type": "adjustment.created"}).encode()
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
                "entitlements": {
                    "ai_draft_generations": {"enabled": True, "monthly_limit": 250},
                    "email_sends": {"enabled": True, "monthly_limit": 1000},
                    "website_audits": {"enabled": True, "monthly_limit": 25},
                    "whatsapp_sends": {"enabled": False, "monthly_limit": 0},
        "prospect_research": {"enabled": True, "monthly_limit": 100},
                },
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

def test_entitlement_validator_rejects_malformed_or_missing_required_policies():
    from app.api.paddle_routes import _valid_entitlements

    assert not _valid_entitlements({})
    assert not _valid_entitlements({"email_sends": {"enabled": True, "monthly_limit": 10}})
    # Search consumes its own quota, so a plan without this policy must fail closed.
    assert not _valid_entitlements({
        "ai_draft_generations": {"enabled": True, "monthly_limit": 10},
        "email_sends": {"enabled": True, "monthly_limit": 10},
        "website_audits": {"enabled": True, "monthly_limit": 10},
        "whatsapp_sends": {"enabled": False, "monthly_limit": 0},
    })
    assert not _valid_entitlements({
        "ai_draft_generations": {"enabled": True, "monthly_limit": True},
        "email_sends": {"enabled": True, "monthly_limit": 10},
        "website_audits": {"enabled": True, "monthly_limit": 10},
        "whatsapp_sends": {"enabled": False, "monthly_limit": 0},
                    "prospect_research": {"enabled": True, "monthly_limit": 100},
    })
    assert _valid_entitlements({
        "ai_draft_generations": {"enabled": True, "monthly_limit": 10},
        "email_sends": {"enabled": True, "monthly_limit": 10},
        "website_audits": {"enabled": True, "monthly_limit": None},
        "whatsapp_sends": {"enabled": False, "monthly_limit": 0},
                    "prospect_research": {"enabled": True, "monthly_limit": 100},
    })


def test_paddle_customer_id_validation_rejects_path_and_query_injection():
    from app.api.paddle_routes import _valid_customer_id

    assert _valid_customer_id("ctm_01h123ABCxyz")
    assert not _valid_customer_id("ctm_")
    assert not _valid_customer_id("ctm_abc/../subscriptions")
    assert not _valid_customer_id("ctm_abc?include=secret")
    assert not _valid_customer_id("ctm_abc#fragment")
    assert not _valid_customer_id("ctm_abc:443")
    assert not _valid_customer_id("ctm_" + "a" * 101)
    assert not _valid_customer_id(None)

def test_paddle_webhook_rejects_oversized_streamed_payload_before_signature(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", "integration-secret")
    body = b"x" * 1_000_001
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/billing/paddle/webhook",
            headers={"Paddle-Signature": "ts=1;h1=invalid"},
            content=body,
        )
    assert response.status_code == 413
    assert response.json()["detail"] == "webhook_payload_too_large"

def test_database_billing_catalog_rejects_duplicate_provider_price_ids(monkeypatch):
    import asyncio
    import pytest
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.api import paddle_routes

    policy = {
        "ai_draft_generations": {"enabled": True, "monthly_limit": 10},
        "email_sends": {"enabled": True, "monthly_limit": 10},
        "website_audits": {"enabled": True, "monthly_limit": 10},
        "whatsapp_sends": {"enabled": False, "monthly_limit": 0},
        "prospect_research": {"enabled": True, "monthly_limit": 10},
    }
    rows = [
        {"slug": "starter", "name": "Starter", "description": "", "price_id": "pri_duplicate",
         "display_price": "$29", "currency": "USD", "billing_interval": "month",
         "entitlements": policy, "active": True},
        {"slug": "growth", "name": "Growth", "description": "", "price_id": "pri_duplicate",
         "display_price": "$79", "currency": "USD", "billing_interval": "month",
         "entitlements": policy, "active": True},
    ]

    class Connection:
        async def fetch(self, query):
            return rows

    class Acquire:
        async def __aenter__(self):
            return Connection()
        async def __aexit__(self, *args):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db_pool=Pool())))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(paddle_routes._effective_plans(request))
    assert exc.value.status_code == 503
    assert exc.value.detail == "billing_plan_catalog_invalid"




def test_subscription_items_require_exactly_one_configured_base_plan():
    import pytest
    from app.api.paddle_routes import _subscription_price_ids

    assert _subscription_price_ids([
        {"price": {"id": "pri_starter"}, "quantity": 1}
    ]) == {"pri_starter"}
    for items in (
        None,
        [],
        [{"price": {"id": "pri_starter"}, "quantity": 1},
         {"price": {"id": "pri_addon"}, "quantity": 1}],
        [{"price": {"id": "pri_starter"}, "quantity": 2}],
        [{"price": {"id": "pri_starter"}, "quantity": True}],
        [{"price": {"id": "invalid"}, "quantity": 1}],
        [{"price": {}, "quantity": 1}],
    ):
        with pytest.raises(ValueError, match="subscription_items_unsupported"):
            _subscription_price_ids(items)

def test_transaction_workspace_mapping_rejects_custom_data_conflicting_with_subscription():
    import asyncio
    import pytest
    from app.api.paddle_routes import _resolve_transaction_workspace

    class Connection:
        async def fetchval(self, query, subscription_id):
            assert subscription_id == "sub_bound"
            return "workspace-owner"

    class Acquire:
        async def __aenter__(self):
            return Connection()
        async def __aexit__(self, *args):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    with pytest.raises(ValueError, match="transaction_workspace_mapping_conflict"):
        asyncio.run(_resolve_transaction_workspace(Pool(), "sub_bound", "workspace-attacker"))


def test_transaction_workspace_mapping_uses_existing_subscription_binding():
    import asyncio
    from app.api.paddle_routes import _resolve_transaction_workspace

    class Connection:
        async def fetchval(self, query, subscription_id):
            return "workspace-owner"

    class Acquire:
        async def __aenter__(self):
            return Connection()
        async def __aexit__(self, *args):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    assert asyncio.run(_resolve_transaction_workspace(Pool(), "sub_bound", "workspace-owner")) == "workspace-owner"
    assert asyncio.run(_resolve_transaction_workspace(Pool(), "sub_bound", None)) == "workspace-owner"


def test_initial_transaction_can_use_checkout_workspace_before_subscription_webhook():
    import asyncio
    from app.api.paddle_routes import _resolve_transaction_workspace

    class Connection:
        async def fetchval(self, query, subscription_id):
            return None

    class Acquire:
        async def __aenter__(self):
            return Connection()
        async def __aexit__(self, *args):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    assert asyncio.run(_resolve_transaction_workspace(Pool(), "sub_new", "workspace-new")) == "workspace-new"

def test_paddle_payment_failed_webhook_records_transaction_without_changing_subscription(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    secret = "integration-secret"
    recorded = {}

    class BillingStore:
        async def record_verified_transaction(self, **kwargs):
            recorded.update(kwargs)
            return {"outcome": "applied"}

        async def apply_verified_event(self, event):
            raise AssertionError("transaction payment failure must not mutate subscription entitlements")

    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", secret)
    with TestClient(app) as client:
        app.state.db_pool = object()
        app.state.billing_lifecycle_store = BillingStore()
        payload = {
            "event_id": "evt_transaction_payment_failed",
            "event_type": "transaction.payment_failed",
            "occurred_at": "2026-10-31T12:05:00Z",
            "data": {
                "id": "txn_payment_failed_route",
                "subscription_id": None,
                "custom_data": {"workspace_id": "workspace-route"},
                "invoice_number": "INV-FAILED-ROUTE",
                "currency_code": "USD",
                "details": {"totals": {"total": "2599"}},
            },
        }
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/billing/paddle/webhook",
            headers={"Paddle-Signature": _signed(body, secret)},
            content=body,
        )

    assert response.status_code == 200
    assert response.json() == {"received": True, "outcome": "applied"}
    assert recorded["status"] == "payment_failed"
    assert recorded["transaction_id"] == "txn_payment_failed_route"
    assert recorded["workspace_id"] == "workspace-route"



def test_paddle_transaction_webhook_persists_only_signature_verified_normalized_fields(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    secret = "integration-secret"
    captured = {}

    class BillingStore:
        async def record_verified_transaction(self, **kwargs):
            captured.update(kwargs)
            return {"outcome": "applied"}

    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", secret)
    with TestClient(app) as client:
        app.state.db_pool = object()
        app.state.billing_lifecycle_store = BillingStore()
        payload = {
            "event_id": "evt_transaction_route",
            "event_type": "transaction.completed",
            "occurred_at": "2026-10-31T12:00:00Z",
            "data": {
                "id": "txn_route_123",
                "subscription_id": None,
                "custom_data": {"workspace_id": "workspace-route"},
                "invoice_number": "INV-ROUTE-123",
                "currency_code": "USD",
                "details": {"totals": {"total": "2599"}},
            },
        }
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/billing/paddle/webhook",
            headers={"Paddle-Signature": _signed(body, secret)},
            content=body,
        )

    assert response.status_code == 200
    assert response.json() == {"received": True, "outcome": "applied"}
    assert captured == {
        "event_id": "evt_transaction_route",
        "event_created_at": datetime.fromisoformat("2026-10-31T12:00:00+00:00"),
        "transaction_id": "txn_route_123",
        "workspace_id": "workspace-route",
        "subscription_id": None,
        "invoice_number": "INV-ROUTE-123",
        "status": "completed",
        "currency_code": "USD",
        "total_minor": "2599",
    }


def test_paddle_subscription_trialing_webhook_updates_subscription_status(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    secret = "integration-secret"
    captured = {}

    class BillingStore:
        async def apply_verified_event(self, event):
            captured["event"] = event
            return {"outcome": "applied"}

    async def fake_effective_plans(request, *, include_inactive=False):
        return {
            "starter": {
                "price_id": "pri_trialing",
                "entitlements": {
                    "ai_draft_generations": {"enabled": True, "monthly_limit": 10},
                    "email_sends": {"enabled": True, "monthly_limit": 10},
                    "website_audits": {"enabled": True, "monthly_limit": 10},
                    "whatsapp_sends": {"enabled": False, "monthly_limit": 0},
                    "prospect_research": {"enabled": True, "monthly_limit": 10},
                },
            }
        }

    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", secret)
    monkeypatch.setattr(paddle_routes, "_effective_plans", fake_effective_plans)
    with TestClient(app) as client:
        app.state.billing_lifecycle_store = BillingStore()
        payload = {
            "event_id": "evt_subscription_trialing",
            "event_type": "subscription.trialing",
            "occurred_at": "2026-10-31T12:00:00Z",
            "data": {
                "id": "sub_trialing_route",
                "status": "trialing",
                "custom_data": {"workspace_id": "workspace-trialing", "plan_id": "starter"},
                "items": [{"price": {"id": "pri_trialing"}, "quantity": 1}],
                "current_billing_period": {
                    "starts_at": "2026-10-31T12:00:00Z",
                    "ends_at": "2026-11-30T12:00:00Z",
                },
            },
        }
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/billing/paddle/webhook",
            headers={"Paddle-Signature": _signed(body, secret)},
            content=body,
        )

    assert response.status_code == 200
    assert response.json() == {"received": True, "outcome": "applied"}
    assert captured["event"].subscription_status == "trialing"
    assert captured["event"].workspace_id == "workspace-trialing"
    assert captured["event"].provider_subscription_id == "sub_trialing_route"


def test_paddle_transaction_past_due_webhook_persists_current_transaction_state(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    secret = "integration-secret"
    recorded = {}

    class BillingStore:
        async def record_verified_transaction(self, **kwargs):
            recorded.update(kwargs)
            return {"outcome": "applied"}

        async def apply_verified_event(self, event):
            raise AssertionError("transaction past due must not independently mutate subscription entitlements")

    class Connection:
        async def fetchval(self, query, subscription_id):
            assert subscription_id == "sub_past_due"
            return "workspace-past-due"

    class Acquire:
        async def __aenter__(self):
            return Connection()
        async def __aexit__(self, *args):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", secret)
    with TestClient(app) as client:
        app.state.db_pool = Pool()
        app.state.billing_lifecycle_store = BillingStore()
        payload = {
            "event_id": "evt_transaction_past_due",
            "event_type": "transaction.past_due",
            "occurred_at": "2026-10-31T12:06:00Z",
            "data": {
                "id": "txn_past_due_route",
                "subscription_id": "sub_past_due",
                "invoice_number": None,
                "currency_code": "USD",
                "details": {"totals": {"total": "2599"}},
            },
        }
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/billing/paddle/webhook",
            headers={"Paddle-Signature": _signed(body, secret)},
            content=body,
        )

    assert response.status_code == 200
    assert response.json() == {"received": True, "outcome": "applied"}
    assert recorded["status"] == "past_due"
    assert recorded["workspace_id"] == "workspace-past-due"
    assert recorded["transaction_id"] == "txn_past_due_route"


def test_paddle_transaction_updated_enriches_invoice_number_without_changing_paid_state(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    secret = "integration-secret"
    captured = {}

    class BillingStore:
        async def record_verified_transaction(self, **kwargs):
            captured.update(kwargs)
            return {"outcome": "applied"}

    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", secret)
    with TestClient(app) as client:
        app.state.db_pool = object()
        app.state.billing_lifecycle_store = BillingStore()
        payload = {
            "event_id": "evt_transaction_updated_invoice",
            "event_type": "transaction.updated",
            "occurred_at": "2026-10-31T12:10:00Z",
            "data": {
                "id": "txn_updated_invoice",
                "status": "completed",
                "subscription_id": None,
                "custom_data": {"workspace_id": "workspace-updated"},
                "invoice_number": "INV-UPDATED-123",
                "currency_code": "USD",
                "details": {"totals": {"total": "2599"}},
            },
        }
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/billing/paddle/webhook",
            headers={"Paddle-Signature": _signed(body, secret)},
            content=body,
        )

    assert response.status_code == 200
    assert response.json() == {"received": True, "outcome": "applied"}
    assert captured["status"] == "completed"
    assert captured["invoice_number"] == "INV-UPDATED-123"
    assert captured["transaction_id"] == "txn_updated_invoice"


def test_paddle_transaction_updated_ignores_nonfinancial_status(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    secret = "integration-secret"
    monkeypatch.setattr(paddle_routes.settings, "paddle_webhook_secret", secret)
    with TestClient(app) as client:
        payload = {
            "event_id": "evt_transaction_updated_ready",
            "event_type": "transaction.updated",
            "occurred_at": "2026-10-31T12:11:00Z",
            "data": {"id": "txn_updated_ready", "status": "ready"},
        }
        body = json.dumps(payload).encode()
        response = client.post(
            "/api/v1/billing/paddle/webhook",
            headers={"Paddle-Signature": _signed(body, secret)},
            content=body,
        )

    assert response.status_code == 200
    assert response.json() == {"received": True, "outcome": "ignored"}


def test_customer_portal_endpoint_uses_authorized_workspace_customer_and_csrf(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    calls = {}
    class AuthStore:
        async def authorize_workspace(self, **kwargs):
            calls["authorization"] = kwargs
            return True

    class Connection:
        async def fetchval(self, query, workspace_id):
            calls["workspace_query"] = workspace_id
            return "ctm_workspace_customer"

    class Acquire:
        async def __aenter__(self):
            return Connection()
        async def __aexit__(self, *args):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    class ProviderResponse:
        status_code = 201
        def json(self):
            return {"data": {"urls": {"general": {
                "overview": "https://customer-portal.sandbox.paddle.com/session/owner-test"
            }}}}

    class ProviderClient:
        def __init__(self, timeout):
            calls["timeout"] = timeout
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            calls["provider_url"] = url
            calls["provider_headers"] = kwargs["headers"]
            calls["provider_json"] = kwargs["json"]
            return ProviderResponse()

    async def fake_authenticated(request):
        return AuthStore(), None, {"user_id": "owner-user"}

    def fake_csrf(request, session):
        calls["csrf"] = session["user_id"]

    monkeypatch.setattr(paddle_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(paddle_routes, "_check_csrf", fake_csrf)
    monkeypatch.setattr(paddle_routes.settings, "paddle_environment", "sandbox")
    monkeypatch.setattr(paddle_routes.settings, "paddle_api_key", "sandbox-api-key")
    monkeypatch.setattr(paddle_routes.httpx, "AsyncClient", ProviderClient)

    with TestClient(app) as client:
        app.state.auth_store = AuthStore()
        app.state.db_pool = Pool()
        response = client.post(
            "/api/v1/billing/paddle/portal?workspace_id=workspace-owner"
        )

    assert response.status_code == 200
    assert response.json() == {
        "portal_url": "https://customer-portal.sandbox.paddle.com/session/owner-test"
    }
    assert calls["csrf"] == "owner-user"
    assert calls["authorization"] == {
        "user_id": "owner-user",
        "workspace_id": "workspace-owner",
        "minimum_role": "admin",
    }
    assert calls["workspace_query"] == "workspace-owner"
    assert calls["provider_url"] == (
        "https://sandbox-api.paddle.com/customers/ctm_workspace_customer/portal-sessions"
    )
    assert calls["provider_headers"]["Authorization"] == "Bearer sandbox-api-key"
    assert calls["provider_json"] == {}


def test_customer_portal_endpoint_hides_workspace_from_non_admin(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import paddle_routes
    from app.main import app

    calls = {"provider": False, "database": False}
    class AuthStore:
        async def authorize_workspace(self, **kwargs):
            return False

    class Pool:
        def acquire(self):
            calls["database"] = True
            raise AssertionError("unauthorized workspace must not be queried")

    class ProviderClient:
        def __init__(self, timeout):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, *args, **kwargs):
            calls["provider"] = True
            raise AssertionError("unauthorized workspace must not contact Paddle")

    async def fake_authenticated(request):
        return AuthStore(), None, {"user_id": "other-user"}

    monkeypatch.setattr(paddle_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(paddle_routes, "_check_csrf", lambda request, session: None)
    monkeypatch.setattr(paddle_routes.settings, "paddle_api_key", "sandbox-api-key")
    monkeypatch.setattr(paddle_routes.httpx, "AsyncClient", ProviderClient)

    with TestClient(app) as client:
        app.state.auth_store = AuthStore()
        app.state.db_pool = Pool()
        response = client.post(
            "/api/v1/billing/paddle/portal?workspace_id=workspace-private"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "workspace_not_found"
    assert calls == {"provider": False, "database": False}
