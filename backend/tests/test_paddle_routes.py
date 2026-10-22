from __future__ import annotations

import hashlib
import hmac
import json
import time

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
