import pytest
from types import SimpleNamespace
from app.services.email_delivery import EmailDeliveryNotConfigured, SMTPEmailDelivery, verification_url

@pytest.mark.parametrize("origin", ["http://example.com", "https://user:pass@example.com", "https://example.com/?x=1", "https://example.com/#fragment", ""])
def test_verification_url_requires_clean_https_origin(origin):
    with pytest.raises(ValueError, match="public_https_origin_required"):
        verification_url("opaque-token", origin)

def test_verification_url_encodes_token():
    assert verification_url("token+/=", "https://app.example/") == "https://app.example/verify-email?token=token%2B%2F%3D"

def test_smtp_fails_closed_when_not_configured():
    config = SimpleNamespace(smtp_host=None, smtp_username=None, smtp_password=None, smtp_from_email=None, smtp_port=587, smtp_starttls=True, public_base_url="https://app.example", smtp_from_name="Test")
    with pytest.raises(EmailDeliveryNotConfigured): SMTPEmailDelivery(config)._validate_configuration()

def test_smtp_requires_tls():
    config = SimpleNamespace(smtp_host="smtp.example", smtp_username="user", smtp_password="secret", smtp_from_email="no-reply@example.com", smtp_port=587, smtp_starttls=False, public_base_url="https://app.example", smtp_from_name="Test")
    with pytest.raises(EmailDeliveryNotConfigured): SMTPEmailDelivery(config)._validate_configuration()