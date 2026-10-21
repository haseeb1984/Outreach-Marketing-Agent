import inspect
import pytest
from pydantic import ValidationError
from app.api.delivery_routes import EnqueueDelivery

def test_idempotency_key_is_required_and_validated():
 assert EnqueueDelivery(workspace_id="w",idempotency_key="send-001-abc").idempotency_key=="send-001-abc"
 for v in ("","short","bad key","x"*201):
  with pytest.raises(ValidationError): EnqueueDelivery(workspace_id="w",idempotency_key=v)
def test_client_cannot_supply_recipient_or_message_body():
 with pytest.raises(ValidationError):
  EnqueueDelivery(workspace_id="w",idempotency_key="send-001-abc",auto_send=True,recipient="x@example.com")
def test_send_route_uses_store_claim_and_never_client_body():
 from app.api import delivery_routes
 src=inspect.getsource(delivery_routes.send_delivery)
 assert "store.claim" in src and "send_outreach_email" in src and "payload.body" not in src


def test_ambiguous_provider_failure_is_not_reported_as_definite_failure():
 from app.api import delivery_routes
 src=inspect.getsource(delivery_routes.send_delivery)
 assert 'error_code="delivery_outcome_unknown"' in src
 assert 'detail="delivery_outcome_unknown"' in src
 assert 'error_code="provider_delivery_failed"' not in src


def test_smtp_configuration_status_reports_missing_names_only():
 from types import SimpleNamespace
 from app.api.delivery_routes import smtp_configuration_status
 cfg=SimpleNamespace(smtp_host="smtp.example.test",smtp_username="user",smtp_password="super-secret-never-return",
  smtp_from_email="sender@example.test",smtp_port=587,smtp_starttls=True)
 status=smtp_configuration_status(cfg)
 assert status["configuration_complete"] is True
 assert status["missing_fields"] == []
 assert status["connection_tested"] is False
 assert "super-secret-never-return" not in repr(status)


def test_smtp_configuration_status_fails_closed_when_tls_or_credentials_missing():
 from types import SimpleNamespace
 from app.api.delivery_routes import smtp_configuration_status
 cfg=SimpleNamespace(smtp_host="",smtp_username="user",smtp_password=None,
  smtp_from_email="sender@example.test",smtp_port=0,smtp_starttls=False)
 status=smtp_configuration_status(cfg)
 assert status["configuration_complete"] is False
 assert {"SMTP_HOST","SMTP_PASSWORD","SMTP_PORT","SMTP_STARTTLS"}.issubset(set(status["missing_fields"]))


def test_whatsapp_configuration_status_reports_missing_names_and_never_values():
 from types import SimpleNamespace
 from app.api.delivery_routes import whatsapp_configuration_status
 cfg=SimpleNamespace(meta_whatsapp_access_token="private-access-token",meta_whatsapp_app_secret="private-app-secret",
  meta_whatsapp_webhook_verify_token="private-verify-token",meta_whatsapp_phone_number_id="12345",meta_whatsapp_waba_id="67890")
 status=whatsapp_configuration_status(cfg)
 assert status["configuration_complete"] is True
 assert status["missing_fields"] == []
 assert status["live_send_enabled"] is False
 assert status["webhook_signature_verification_implemented"] is False
 assert "private-access-token" not in repr(status)
 assert "private-app-secret" not in repr(status)

def test_whatsapp_configuration_status_fails_closed_until_adapter_and_assets_are_ready():
 from types import SimpleNamespace
 from app.api.delivery_routes import whatsapp_configuration_status
 cfg=SimpleNamespace(meta_whatsapp_access_token=None,meta_whatsapp_app_secret=" ",
  meta_whatsapp_webhook_verify_token=None,meta_whatsapp_phone_number_id=None,meta_whatsapp_waba_id=None)
 status=whatsapp_configuration_status(cfg)
 assert status["configuration_complete"] is False
 assert len(status["missing_fields"]) == 5
 assert status["live_send_enabled"] is False
 assert status["coexistence_onboarding_required"] is True



def test_send_route_reserves_server_owned_email_quota_before_provider_call():
 from app.api import delivery_routes
 src=inspect.getsource(delivery_routes.send_delivery)
 assert src.index("subscriptions.reserve_usage") < src.index("store.claim")
 assert 'feature="email_sends"' in src
 assert 'detail="quota_exhausted"' not in src  # response uses the trusted decision reason
 assert 'outcome="consumed"' in src
 assert 'outcome="released"' in src


def test_send_route_does_not_release_quota_for_ambiguous_provider_outcome():
 from app.api import delivery_routes
 src=inspect.getsource(delivery_routes.send_delivery)
 ambiguous=src[src.index("except EmailDeliveryFailed"):src.index("if not await store.finish")]
 assert 'error_code="delivery_outcome_unknown"' in ambiguous
 assert 'outcome="consumed"' in ambiguous
 assert 'outcome="released"' not in ambiguous
