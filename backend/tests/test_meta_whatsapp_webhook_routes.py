from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.api import meta_whatsapp_webhook_routes
from app.main import app


def _signed(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return "sha256=" + digest


def _payload() -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {"id": "waba-1", "changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "phone-1"},
                "messages": [{"id": "wamid-1", "type": "text"}],
            }}]},
            {"id": "waba-2", "changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "phone-2"},
                "statuses": [{"id": "wamid-2", "status": "delivered"}],
            }}]},
        ],
    }


class _Connection:
    def __init__(self):
        self.duplicate = False
        self.rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def transaction(self):
        return self

    async def fetchrow(self, query, *args):
        self.rows.append(args)
        return None if self.duplicate else {"id": len(self.rows)}


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *args):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


def test_meta_webhook_verification_requires_exact_token(monkeypatch):
    monkeypatch.setattr(meta_whatsapp_webhook_routes.settings, "meta_whatsapp_webhook_verify_token", "v" * 40)
    with TestClient(app) as client:
        accepted = client.get("/api/v1/webhooks/meta/whatsapp", params={
            "hub.mode": "subscribe", "hub.verify_token": "v" * 40, "hub.challenge": "challenge-123",
        })
        rejected = client.get("/api/v1/webhooks/meta/whatsapp", params={
            "hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "challenge-123",
        })
    assert accepted.status_code == 200
    assert accepted.text == "challenge-123"
    assert accepted.headers["cache-control"] == "no-store"
    assert rejected.status_code == 403


def test_meta_webhook_rejects_invalid_signature_before_persistence(monkeypatch):
    monkeypatch.setattr(meta_whatsapp_webhook_routes.settings, "meta_whatsapp_app_secret", "s" * 40)
    connection = _Connection()
    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        response = client.post("/api/v1/webhooks/meta/whatsapp",
            headers={"x-hub-signature-256": "sha256=invalid"}, json=_payload())
    assert response.status_code == 401
    assert connection.rows == []


def test_meta_webhook_splits_phone_numbers_and_deduplicates(monkeypatch):
    secret = "s" * 40
    monkeypatch.setattr(meta_whatsapp_webhook_routes.settings, "meta_whatsapp_app_secret", secret)
    body = json.dumps(_payload(), separators=(",", ":")).encode("utf-8")
    connection = _Connection()
    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        headers = {"x-hub-signature-256": _signed(body, secret), "content-type": "application/json"}
        first = client.post("/api/v1/webhooks/meta/whatsapp", content=body, headers=headers)
        connection.duplicate = True
        second = client.post("/api/v1/webhooks/meta/whatsapp", content=body, headers=headers)
    assert first.status_code == 202
    assert first.json() == {"accepted": True, "events_accepted": 2, "duplicates": 0}
    assert second.status_code == 202
    assert second.json() == {"accepted": True, "events_accepted": 0, "duplicates": 2}
    assert [row[1] for row in connection.rows[:2]] == ["phone-1", "phone-2"]
    assert [row[2] for row in connection.rows[:2]] == ["messages", "statuses"]


def test_meta_webhook_rejects_oversized_body(monkeypatch):
    monkeypatch.setattr(meta_whatsapp_webhook_routes.settings, "meta_whatsapp_app_secret", "s" * 40)
    with TestClient(app) as client:
        response = client.post("/api/v1/webhooks/meta/whatsapp",
            content=b"x" * (meta_whatsapp_webhook_routes.MAX_WEBHOOK_BYTES + 1))
    assert response.status_code == 413
    assert response.json()["detail"] == "payload_too_large"
