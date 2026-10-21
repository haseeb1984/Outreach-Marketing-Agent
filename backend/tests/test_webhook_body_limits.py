from fastapi.testclient import TestClient

from app.api.conversation_routes import MAX_WEBHOOK_BYTES
from app.core.config import settings
from app.main import app


def test_inbound_webhook_rejects_oversized_body_before_signature_parsing(monkeypatch):
    monkeypatch.setattr(settings, "outreach_webhook_secret", "test-secret-" + "x" * 32)
    oversized_body = b"x" * (MAX_WEBHOOK_BYTES + 1)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/webhooks/inbound-replies",
            content=oversized_body,
            headers={
                "Content-Type": "application/json",
                "X-Outreach-Signature": "sha256=invalid",
            },
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "payload_too_large"}
