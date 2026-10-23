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
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = FakeStore()
        app.state.auth_rate_limiter = FakeLimiter()
        client.cookies.set("__Host-oma_session", "session-token")
        yield client


def test_provider_status_requires_auth_and_never_returns_secrets(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(config.settings, "smtp_username", "mailer")
    monkeypatch.setattr(config.settings, "smtp_password", "never-return-this")
    monkeypatch.setattr(config.settings, "smtp_from_email", "noreply@example.test")
    monkeypatch.setattr(config.settings, "smtp_starttls", True)

    with _client(monkeypatch) as client:
        response = client.get("/api/v1/integrations/status?workspace_id=workspace-1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["email"]["configuration_complete"] is True
    assert payload["whatsapp"]["live_send_enabled"] is False
    assert "never-return-this" not in response.text
    assert "smtp.example.test" not in response.text


def test_provider_status_hides_non_member_workspace(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/api/v1/integrations/status?workspace_id=other-workspace")
    assert response.status_code == 404
    assert response.json()["detail"] == "workspace_not_found"


def test_smtp_test_requires_csrf_and_never_sends_email(monkeypatch):
    from app.api import delivery_routes

    from app.core import config

    monkeypatch.setattr(delivery_routes.settings, "environment", "production")
    monkeypatch.setattr(config.settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(config.settings, "smtp_port", 587)
    monkeypatch.setattr(config.settings, "smtp_username", "mailer")
    monkeypatch.setattr(config.settings, "smtp_password", "test-only-not-a-real-secret")
    monkeypatch.setattr(config.settings, "smtp_from_email", "noreply@example.test")
    monkeypatch.setattr(config.settings, "smtp_starttls", True)
    calls = []

    async def fake_test_connection(self):
        calls.append("tested")

    monkeypatch.setattr(delivery_routes.SMTPEmailDelivery, "test_connection", fake_test_connection)
    with _client(monkeypatch) as client:
        rejected = client.post(
            "/api/v1/integrations/smtp/test?workspace_id=workspace-1",
            headers={"Origin": "https://app.example.test"},
        )
        assert rejected.status_code == 403

        accepted = client.post(
            "/api/v1/integrations/smtp/test?workspace_id=workspace-1",
            headers={
                "Origin": "https://app.example.test",
                "X-CSRF-Token": "c" * 43,
            },
        )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "authenticated"
    assert accepted.json()["email_sent"] is False
    assert "no email was sent" in accepted.json()["message"].lower()
    assert calls == ["tested"]
