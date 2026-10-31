from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api import auth_routes
from app.main import app


class FakeAuthStore:
    def __init__(self, allowed_workspace: str = "workspace-1"):
        self.allowed_workspace = allowed_workspace

    async def authenticate_session(self, token):
        return {
            "user_id": "user-1",
            "email": "viewer@example.test",
            "session_id": "session-1",
            "csrf_token_sha256": auth_routes.csrf_token_digest("c" * 43),
        }

    async def authorize_workspace(self, *, user_id, workspace_id, minimum_role):
        assert user_id == "user-1"
        assert minimum_role == "viewer"
        return workspace_id == self.allowed_workspace


class FakeLimiter:
    async def consume(self, **kwargs):
        return {
            "allowed": True,
            "remaining": 9,
            "reset_at": datetime.now(timezone.utc) + timedelta(minutes=15),
        }


class FakeConnection:
    def __init__(self, account, templates):
        self.account = account
        self.templates = templates
        self.fetchrow_calls = []
        self.fetch_calls = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self.account

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self.templates


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_template_catalogue_is_workspace_scoped_and_never_exposes_credentials(monkeypatch):
    account_id = uuid4()
    verified_at = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
    connection = FakeConnection(
        {"id": account_id},
        [{
            "template_name": "welcome_offer",
            "language_code": "en_US",
            "category": "marketing",
            "status": "approved",
            "provider_status": "APPROVED",
            "verified_at": verified_at,
            "updated_at": verified_at,
        }],
    )
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = FakeAuthStore()
        app.state.auth_rate_limiter = FakeLimiter()
        app.state.db_pool = FakePool(connection)
        client.cookies.set("__Host-oma_session", "session-token")
        response = client.get(
            f"/api/v1/integrations/whatsapp/accounts/{account_id}/templates"
            "?workspace_id=workspace-1"
        )

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["template_name"] == "welcome_offer"
    assert response.json()["items"][0]["status"] == "approved"
    assert "encrypted_access_token" not in response.text
    account_query, account_args = connection.fetchrow_calls[0]
    template_query, template_args = connection.fetch_calls[0]
    assert "WHERE id=$1 AND workspace_id=$2" in account_query
    assert account_args == (account_id, "workspace-1")
    assert "WHERE workspace_id=$1 AND account_id=$2" in template_query
    assert template_args == ("workspace-1", account_id)


def test_template_catalogue_hides_another_workspace_account(monkeypatch):
    account_id = uuid4()
    connection = FakeConnection(None, [])
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = FakeAuthStore()
        app.state.auth_rate_limiter = FakeLimiter()
        app.state.db_pool = FakePool(connection)
        client.cookies.set("__Host-oma_session", "session-token")
        response = client.get(
            f"/api/v1/integrations/whatsapp/accounts/{account_id}/templates"
            "?workspace_id=workspace-1"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "whatsapp_account_not_found"
    assert connection.fetch_calls == []


def test_template_catalogue_rejects_non_member_workspace(monkeypatch):
    connection = FakeConnection(None, [])
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = FakeAuthStore(allowed_workspace="workspace-2")
        app.state.auth_rate_limiter = FakeLimiter()
        app.state.db_pool = FakePool(connection)
        client.cookies.set("__Host-oma_session", "session-token")
        response = client.get(
            f"/api/v1/integrations/whatsapp/accounts/{uuid4()}/templates"
            "?workspace_id=workspace-1"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "workspace_not_found"
    assert connection.fetchrow_calls == []


class FakeActivityConnection:
    def __init__(self, existence_results):
        self.existence_results = iter(existence_results)

    async def fetchval(self, query, *args):
        return next(self.existence_results)

    async def fetch(self, query, *args):
        return []


def test_whatsapp_activity_feed_preserves_not_found_response(monkeypatch):
    connection = FakeActivityConnection([False])
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = FakeAuthStore()
        app.state.auth_rate_limiter = FakeLimiter()
        app.state.db_pool = FakePool(connection)
        client.cookies.set("__Host-oma_session", "session-token")
        response = client.get(
            "/api/v1/integrations/whatsapp/inbox/conversations/"
            "00000000-0000-0000-0000-000000000001/activity",
            params={"workspace_id": "workspace-1"},
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "whatsapp_conversation_not_found"


def test_whatsapp_activity_feed_preserves_invalid_cursor_response(monkeypatch):
    connection = FakeActivityConnection([True, False])
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = FakeAuthStore()
        app.state.auth_rate_limiter = FakeLimiter()
        app.state.db_pool = FakePool(connection)
        client.cookies.set("__Host-oma_session", "session-token")
        response = client.get(
            "/api/v1/integrations/whatsapp/inbox/conversations/"
            "00000000-0000-0000-0000-000000000001/activity",
            params={
                "workspace_id": "workspace-1",
                "before_id": "00000000-0000-0000-0000-000000000002",
            },
        )
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_before_activity_id"
