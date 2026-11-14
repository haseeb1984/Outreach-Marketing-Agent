from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api import auth_routes
from app.main import app


class FakeStore:
    async def authenticate_session(self, token):
        return {
            "user_id": "user-1",
            "email": "owner@example.test",
            "session_id": "session-1",
            "csrf_token_sha256": auth_routes.csrf_token_digest("c" * 43),
        }

    async def authorize_workspace(self, *, user_id, workspace_id, minimum_role):
        return workspace_id == "workspace-1" and minimum_role in {"viewer", "admin"}


class FakeLimiter:
    async def consume(self, **kwargs):
        return {
            "allowed": True,
            "remaining": 9,
            "reset_at": datetime.now(timezone.utc) + timedelta(minutes=15),
        }


@contextmanager
def _client(monkeypatch):
    from app.api import delivery_routes

    async def list_workspace_accounts(self, *, workspace_id):
        return []

    monkeypatch.setattr(delivery_routes.SMTPAccountStore, "list_accounts", list_workspace_accounts)
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = FakeStore()
        app.state.auth_rate_limiter = FakeLimiter()
        app.state.db_pool = object()
        client.cookies.set("__Host-oma_session", "session-token")
        yield client


def test_provider_status_uses_workspace_accounts_not_platform_environment(monkeypatch):
    from app.api import delivery_routes
    from app.core import config

    monkeypatch.setattr(config.settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(config.settings, "smtp_username", "mailer")
    monkeypatch.setattr(config.settings, "smtp_password", "never-return-this")
    monkeypatch.setattr(config.settings, "smtp_from_email", "noreply@example.test")
    monkeypatch.setattr(config.settings, "smtp_starttls", True)

    async def active_workspace_account(self, *, workspace_id):
        assert workspace_id == "workspace-1"
        return [{"id": "account-1", "status": "active", "smtp_host": "private.smtp.test"}]

    with _client(monkeypatch) as client:
        monkeypatch.setattr(delivery_routes.SMTPAccountStore, "list_accounts", active_workspace_account)
        response = client.get("/api/v1/integrations/status?workspace_id=workspace-1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["email"]["configuration_complete"] is True
    assert payload["email"]["connection_tested"] is True
    assert payload["email"]["active_workspace_accounts"] == 1
    assert payload["whatsapp"]["live_send_enabled"] is False
    assert "never-return-this" not in response.text
    assert "smtp.example.test" not in response.text
    assert "private.smtp.test" not in response.text


def test_provider_status_hides_non_member_workspace(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/api/v1/integrations/status?workspace_id=other-workspace")
    assert response.status_code == 404
    assert response.json()["detail"] == "workspace_not_found"


def test_legacy_platform_smtp_test_endpoint_is_not_registered():
    from app.api import delivery_routes
    assert not any(
        getattr(route, "path", "") == "/api/v1/integrations/smtp/test"
        for route in delivery_routes.router.routes
    )


def test_provider_status_without_active_workspace_smtp_is_incomplete(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/api/v1/integrations/status?workspace_id=workspace-1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["email"]["configuration_complete"] is False
    assert payload["email"]["connection_tested"] is False
    assert payload["email"]["missing_fields"] == ["ACTIVE_WORKSPACE_SMTP_ACCOUNT"]
