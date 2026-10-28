from __future__ import annotations

from types import SimpleNamespace

import asyncio
import pytest
from fastapi import HTTPException

from app.api import billing_routes


class _AuthStore:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    async def authorize_workspace(self, **kwargs):
        self.calls.append(kwargs)
        return self.allowed


class _SubscriptionStore:
    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error
        self.calls = []

    async def get_entitlement(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.decision


def _request(auth_store=None, subscription_store=None):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                auth_store=auth_store,
                subscription_store=subscription_store,
            )
        )
    )


def _authenticated(monkeypatch):
    async def fake_authenticated(_request):
        return None, None, {"user_id": "user-1", "email": "person@example.test"}
    monkeypatch.setattr(billing_routes, "_authenticated", fake_authenticated)


def test_entitlement_endpoint_returns_trusted_decision_and_scopes_workspace(monkeypatch):
    _authenticated(monkeypatch)
    auth = _AuthStore()
    decision = SimpleNamespace(allowed=True, reason="entitled", remaining=7)
    subscriptions = _SubscriptionStore(decision=decision)

    result = asyncio.run(
        billing_routes.get_workspace_entitlement(
            _request(auth, subscriptions), workspace_id="workspace-1", feature="email_outreach"
        )
    )

    assert result == {
        "workspace_id": "workspace-1",
        "feature": "email_outreach",
        "allowed": True,
        "reason": "entitled",
        "remaining": 7,
    }
    assert auth.calls == [{
        "user_id": "user-1", "workspace_id": "workspace-1", "minimum_role": "viewer"
    }]
    assert subscriptions.calls == [{"workspace_id": "workspace-1", "feature": "email_outreach"}]


def test_entitlement_endpoint_hides_unauthorized_workspace_and_never_reads_billing(monkeypatch):
    _authenticated(monkeypatch)
    auth = _AuthStore(allowed=False)
    subscriptions = _SubscriptionStore(decision=SimpleNamespace(allowed=True, reason="entitled", remaining=7))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            billing_routes.get_workspace_entitlement(
                _request(auth, subscriptions), workspace_id="other-workspace", feature="email_outreach"
            )
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "workspace_not_found"
    assert subscriptions.calls == []


def test_entitlement_endpoint_fails_closed_when_auth_store_missing(monkeypatch):
    _authenticated(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            billing_routes.get_workspace_entitlement(
                _request(), workspace_id="workspace-1", feature="email_outreach"
            )
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "authentication_not_configured"


def test_entitlement_endpoint_fails_closed_when_billing_store_missing(monkeypatch):
    _authenticated(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            billing_routes.get_workspace_entitlement(
                _request(_AuthStore()), workspace_id="workspace-1", feature="email_outreach"
            )
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "billing_service_not_configured"


def test_entitlement_endpoint_redacts_billing_store_errors(monkeypatch):
    _authenticated(monkeypatch)
    subscriptions = _SubscriptionStore(error=RuntimeError("sensitive database details"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            billing_routes.get_workspace_entitlement(
                _request(_AuthStore(), subscriptions), workspace_id="workspace-1", feature="email_outreach"
            )
        )

    assert exc.value.status_code == 503
    assert exc.value.detail == "billing_status_unavailable"
    assert "sensitive database details" not in str(exc.value.detail)
