from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import prospect_routes


def test_prospect_urls_must_use_https_and_credentials_are_rejected():
    assert prospect_routes._https_url("https://example.com/about") == "https://example.com/about"
    for value in (
        "http://example.com",
        "https://user:password@example.com",
        "javascript:alert(1)",
        "not-a-url",
    ):
        with pytest.raises(ValueError):
            prospect_routes._https_url(value)


def test_prospect_stage_is_allowlisted():
    assert prospect_routes.ProspectUpdate(workspace_id="w", stage="qualified").stage == "qualified"
    with pytest.raises(ValueError):
        prospect_routes.ProspectUpdate(workspace_id="w", stage="sent-everywhere")


def test_workspace_authorization_hides_unavailable_workspace():
    import asyncio

    class AuthStore:
        async def authorize_workspace(self, **kwargs):
            return False

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(auth_store=AuthStore())),
        cookies={prospect_routes._authenticated.__globals__["cookie_policy"].name: "session"},
    )

    async def authenticated(_request):
        return AuthStore(), "session", {"user_id": "00000000-0000-0000-0000-000000000001"}

    original = prospect_routes._authenticated
    prospect_routes._authenticated = authenticated
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(prospect_routes._authorize(request, "another-workspace", "viewer"))
        assert exc.value.status_code == 404
    finally:
        prospect_routes._authenticated = original


def test_prospect_create_schema_rejects_unbounded_or_extra_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        prospect_routes.ProspectCreate(
            workspace_id="workspace",
            name="Prospect",
            company="Company",
            website_url="https://example.com",
            evidence_url="https://example.com/source",
            fit_reason="Relevant public evidence",
            unapproved_send=True,
        )
    with pytest.raises(ValidationError):
        prospect_routes.ProspectCreate(
            workspace_id="workspace",
            name="Prospect",
            company="Company",
            website_url="http://example.com",
            evidence_url="https://example.com/source",
            fit_reason="Relevant public evidence",
        )



def test_list_prospects_checks_workspace_membership_and_uses_workspace_filter(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    user_id = "00000000-0000-0000-0000-000000000001"

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            assert kwargs["user_id"] == user_id
            assert kwargs["workspace_id"] == "workspace-a"
            assert kwargs["minimum_role"] == "viewer"
            return True

    class FakeProspectStore:
        async def list_prospects(self, **kwargs):
            assert kwargs == {"workspace_id": "workspace-a", "stage": "qualified", "limit": 10, "offset": 0}
            return [{"id": "prospect-1", "workspace_id": "workspace-a", "stage": "qualified"}]

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": user_id}

    monkeypatch.setattr(prospect_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(app.state, "auth_store", FakeAuthStore(), raising=False)
    monkeypatch.setattr(app.state, "prospect_store", FakeProspectStore(), raising=False)
    with TestClient(app) as client:
        response = client.get("/api/v1/prospects", params={
            "workspace_id": "workspace-a", "stage": "qualified", "limit": 10,
        })
    assert response.status_code == 200
    assert response.json()["items"][0]["workspace_id"] == "workspace-a"


def test_create_prospect_uses_authenticated_user_and_requires_csrf_gate(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    user_id = "00000000-0000-0000-0000-000000000001"
    saved = {}

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            return kwargs["user_id"] == user_id and kwargs["workspace_id"] == "workspace-a" and kwargs["minimum_role"] == "member"

    class FakeProspectStore:
        async def create_prospect(self, **kwargs):
            saved.update(kwargs)
            return {"id": "prospect-1", "workspace_id": kwargs["workspace_id"], "created_by": kwargs["created_by"]}

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": user_id}

    monkeypatch.setattr(prospect_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(prospect_routes, "_check_csrf", lambda request, session: None)
    monkeypatch.setattr(app.state, "auth_store", FakeAuthStore(), raising=False)
    monkeypatch.setattr(app.state, "prospect_store", FakeProspectStore(), raising=False)
    payload = {
        "workspace_id": "workspace-a",
        "name": "Jane Example",
        "company": "Example Co",
        "website_url": "https://example.com",
        "evidence_url": "https://example.com/about",
        "fit_reason": "Public page explicitly lists a matching service.",
        "verified_facts": ["The company provides service X."],
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/prospects", json=payload)
    assert response.status_code == 201
    assert saved["created_by"] == user_id
    assert saved["verified_facts"] == ["The company provides service X."]
    assert response.json()["created_by"] == user_id


def test_create_prospect_rejects_cross_workspace_member(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            return False

    class NeverProspectStore:
        async def create_prospect(self, **kwargs):
            raise AssertionError("cross-workspace write must not reach persistence")

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": "00000000-0000-0000-0000-000000000001"}

    monkeypatch.setattr(prospect_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(prospect_routes, "_check_csrf", lambda request, session: None)
    monkeypatch.setattr(app.state, "auth_store", FakeAuthStore(), raising=False)
    monkeypatch.setattr(app.state, "prospect_store", NeverProspectStore(), raising=False)
    payload = {
        "workspace_id": "workspace-b",
        "name": "Jane Example",
        "company": "Example Co",
        "website_url": "https://example.com",
        "evidence_url": "https://example.com/about",
        "fit_reason": "Public page explicitly lists a matching service.",
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/prospects", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "workspace_not_found"
