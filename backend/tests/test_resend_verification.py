from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.api import auth_routes
from app.main import app


def test_resend_verification_is_generic_and_rotates_only_pending_account(monkeypatch):
    sent = []
    class FakeStore:
        async def issue_verification_email(self, *, email):
            if email == "pending@example.test":
                return {
                    "email": email,
                    "verification_token": "v" * 43,
                    "verification_expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
                }
            return None

    class AllowLimiter:
        async def consume(self, **kwargs):
            return {
                "allowed": True,
                "remaining": 9,
                "reset_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            }

    def validate(self):
        return None

    async def fake_send(self, **kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    monkeypatch.setattr(auth_routes.SMTPEmailDelivery, "_validate_configuration", validate)
    monkeypatch.setattr(auth_routes.SMTPEmailDelivery, "send_verification_email", fake_send)
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = FakeStore()
        app.state.auth_rate_limiter = AllowLimiter()
        headers = {"Origin": "https://app.example.test"}
        known = client.post(
            "/api/v1/auth/resend-verification", headers=headers,
            json={"email": "pending@example.test"},
        )
        unknown = client.post(
            "/api/v1/auth/resend-verification", headers=headers,
            json={"email": "unknown@example.test"},
        )
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert len(sent) == 1
        assert sent[0]["recipient"] == "pending@example.test"
        assert sent[0]["token"] == "v" * 43


def test_resend_verification_rejects_untrusted_origin(monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        response = client.post(
            "/api/v1/auth/resend-verification",
            headers={"Origin": "https://attacker.example.test"},
            json={"email": "pending@example.test"},
        )
        assert response.status_code == 403
