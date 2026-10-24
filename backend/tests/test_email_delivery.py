import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.email_delivery import (
    EmailDeliveryFailed,
    EmailDeliveryNotConfigured,
    SMTPEmailDelivery,
    verification_url,
)


@pytest.mark.parametrize("origin", ["http://example.com", "https://user:pass@example.com", "https://example.com/?x=1", "https://example.com/#fragment", ""])
def test_verification_url_requires_clean_https_origin(origin):
    with pytest.raises(ValueError, match="public_https_origin_required"):
        verification_url("opaque-token", origin)


def test_verification_url_encodes_token():
    assert verification_url("token+/=", "https://app.example/") == "https://app.example/api/v1/auth/verify-email?token=token%2B%2F%3D"


def _config(**overrides):
    values = dict(
        smtp_host="smtp.example", smtp_username="user", smtp_password="dummy-secret",
        smtp_from_email="no-reply@example.com", smtp_port=587, smtp_starttls=True,
        public_base_url="https://app.example", smtp_from_name="Test",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_smtp_fails_closed_when_not_configured():
    with pytest.raises(EmailDeliveryNotConfigured):
        SMTPEmailDelivery(_config(smtp_host=None))._validate_configuration()


def test_smtp_requires_tls():
    with pytest.raises(EmailDeliveryNotConfigured):
        SMTPEmailDelivery(_config(smtp_starttls=False))._validate_configuration()


def test_smtp_failure_does_not_expose_provider_exception(monkeypatch):
    delivery = SMTPEmailDelivery(_config())

    def fail(_message):
        raise RuntimeError("AUTH failed for dummy-secret and token=private-token")

    monkeypatch.setattr(delivery, "_send_message", fail)
    with pytest.raises(EmailDeliveryFailed) as caught:
        asyncio.run(delivery.send_verification_email(
            recipient="person@example.com",
            token="a-very-long-dummy-verification-token-123456",
            expires_at=datetime.now(timezone.utc),
        ))
    assert str(caught.value) == "smtp_delivery_failed"
    assert "dummy-secret" not in str(caught.value)
    assert "private-token" not in str(caught.value)
    assert caught.value.__cause__ is None



def test_smtp_connection_uses_tls_auth_and_never_sends_email(monkeypatch):
    import smtplib

    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def ehlo(self): calls.append(("ehlo",))
        def starttls(self): calls.append(("starttls",))
        def login(self, username, password): calls.append(("login", username, password))
        def send_message(self, message): calls.append(("send_message",))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    asyncio.run(SMTPEmailDelivery(_config()).test_connection())
    assert [item[0] for item in calls] == ["connect", "ehlo", "starttls", "ehlo", "login"]
    assert all(item[0] != "send_message" for item in calls)


def test_smtp_connection_failure_is_sanitized(monkeypatch):
    delivery = SMTPEmailDelivery(_config())
    def fail():
        raise RuntimeError("AUTH rejected for dummy-secret")
    monkeypatch.setattr(delivery, "_test_connection", fail)
    with pytest.raises(EmailDeliveryFailed) as caught:
        asyncio.run(delivery.test_connection())
    assert str(caught.value) == "smtp_connection_test_failed"
    assert "dummy-secret" not in str(caught.value)
    assert caught.value.__cause__ is None



def test_password_reset_email_uses_real_line_breaks(monkeypatch):
    delivery = SMTPEmailDelivery(_config())
    captured = {}

    def capture(message):
        captured["body"] = message.get_content()

    monkeypatch.setattr(delivery, "_send_message", capture)
    asyncio.run(delivery.send_password_reset_email(
        recipient="person@example.com",
        token="a-very-long-dummy-reset-token-123456789",
        expires_at=datetime.now(timezone.utc),
    ))
    body = captured["body"]
    assert "\n\n" in body
    assert "\\\\n" not in body


def test_password_reset_email_uses_backend_landing_route(monkeypatch):
    delivery = SMTPEmailDelivery(_config())
    captured = {}

    def capture(message):
        captured["body"] = message.get_content()

    monkeypatch.setattr(delivery, "_send_message", capture)
    asyncio.run(delivery.send_password_reset_email(
        recipient="person@example.com",
        token="a-very-long-dummy-reset-token-123456789",
        expires_at=datetime.now(timezone.utc),
    ))
    assert "https://app.example/api/v1/auth/reset-password?token=" in captured["body"]

def test_workspace_invitation_links_to_authenticated_dashboard(monkeypatch):
    delivery = SMTPEmailDelivery(_config())
    captured = {}

    def capture(message):
        captured["body"] = message.get_content()

    monkeypatch.setattr(delivery, "_send_message", capture)
    asyncio.run(delivery.send_workspace_invitation_email(
        recipient="person@example.com",
        token="opaque-invitation-token-123456789",
        workspace_name="Example Workspace",
        role="member",
        expires_at=datetime.now(timezone.utc),
    ))
    assert "https://app.example/app?invite_token=opaque-invitation-token-123456789" in captured["body"]
    assert "/invitations/accept" not in captured["body"]
