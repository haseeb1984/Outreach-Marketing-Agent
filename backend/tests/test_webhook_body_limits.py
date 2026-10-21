import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.conversation_routes import MAX_WEBHOOK_BYTES, _read_bounded_body
from app.core.config import settings
from app.main import app


class ChunkedRequest:
    headers = {}

    def __init__(self, chunks):
        self.chunks = chunks

    async def stream(self):
        for chunk in self.chunks:
            yield chunk


def test_stream_without_content_length_is_bounded():
    request = ChunkedRequest([b"x" * MAX_WEBHOOK_BYTES, b"x"])

    with pytest.raises(HTTPException) as error:
        asyncio.run(_read_bounded_body(request))

    assert error.value.status_code == 413
    assert error.value.detail == "payload_too_large"


def test_inbound_webhook_rejects_oversized_declared_body_before_signature_parsing(monkeypatch):
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


def test_exact_limit_body_is_accepted():
    request = ChunkedRequest([b"x" * MAX_WEBHOOK_BYTES])

    body = asyncio.run(_read_bounded_body(request))

    assert len(body) == MAX_WEBHOOK_BYTES


def test_invalid_content_length_is_rejected():
    request = ChunkedRequest([b"small"])
    request.headers = {"content-length": "not-a-number"}

    with pytest.raises(HTTPException) as error:
        asyncio.run(_read_bounded_body(request))

    assert error.value.status_code == 400
    assert error.value.detail == "invalid_content_length"
