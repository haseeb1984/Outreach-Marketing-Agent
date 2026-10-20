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


def test_password_reset_email_uses_https_origin_and_hides_smtp_errors(monkeypatch):
    delivery = SMTPEmailDelivery(_config())

    def fail(_message):
        raise RuntimeError("smtp secret and reset token must never leak")

    monkeypatch.setattr(delivery, "_send_message", fail)
    with pytest.raises(EmailDeliveryFailed) as caught:
        asyncio.run(delivery.send_password_reset_email(
            recipient="person@example.com",
            token="r" * 43,
            expires_at=datetime.now(timezone.utc),
        ))
    assert str(caught.value) == "smtp_delivery_failed"
    assert caught.value.__cause__ is None

    delivery = SMTPEmailDelivery(_config(public_base_url="http://insecure.example"))
    with pytest.raises(ValueError, match="public_https_origin_required"):
        asyncio.run(delivery.send_password_reset_email(
            recipient="person@example.com",
            token="r" * 43,
            expires_at=datetime.now(timezone.utc),
        ))
