import inspect
import pytest
from pydantic import ValidationError
from app.api.delivery_routes import EnqueueDelivery

def test_idempotency_key_is_required_and_validated():
 assert EnqueueDelivery(workspace_id="w",idempotency_key="send-001-abc",email_account_id="00000000-0000-0000-0000-000000000001").idempotency_key=="send-001-abc"
 for v in ("","short","bad key","x"*201):
  with pytest.raises(ValidationError): EnqueueDelivery(workspace_id="w",idempotency_key=v,email_account_id="00000000-0000-0000-0000-000000000001")
def test_client_cannot_supply_recipient_or_message_body():
 with pytest.raises(ValidationError):
  EnqueueDelivery(workspace_id="w",idempotency_key="send-001-abc",email_account_id="00000000-0000-0000-0000-000000000001",auto_send=True,recipient="x@example.com")
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


def test_platform_level_smtp_status_and_test_helpers_are_not_exposed():
 from app.api import delivery_routes
 assert not hasattr(delivery_routes, "smtp_configuration_status")
 assert not hasattr(delivery_routes, "test_smtp_connection")
 assert not any(getattr(route, "path", "") == "/api/v1/integrations/smtp/test" for route in delivery_routes.router.routes)


def test_whatsapp_configuration_status_reports_only_platform_meta_prerequisites():
 from types import SimpleNamespace
 from app.api.delivery_routes import whatsapp_configuration_status
 cfg=SimpleNamespace(meta_whatsapp_access_token=None,meta_whatsapp_app_secret="private-app-secret",
  meta_whatsapp_webhook_verify_token="private-verify-token",meta_whatsapp_phone_number_id=None,
  meta_whatsapp_waba_id=None,meta_graph_api_version="v22.0")
 status=whatsapp_configuration_status(cfg)
 assert status["configuration_complete"] is True
 assert status["missing_fields"] == []
 assert status["customer_credentials_are_workspace_scoped"] is True
 assert status["live_send_enabled"] is False
 assert status["webhook_signature_verification_implemented"] is True
 assert "private-app-secret" not in repr(status)
 assert "private-verify-token" not in repr(status)

def test_whatsapp_configuration_status_fails_closed_for_missing_platform_webhook_prerequisites():
 from types import SimpleNamespace
 from app.api.delivery_routes import whatsapp_configuration_status
 cfg=SimpleNamespace(meta_whatsapp_access_token="tenant-token",meta_whatsapp_app_secret=" ",
  meta_whatsapp_webhook_verify_token=None,meta_whatsapp_phone_number_id="tenant-phone",
  meta_whatsapp_waba_id="tenant-waba",meta_graph_api_version=None)
 status=whatsapp_configuration_status(cfg)
 assert status["configuration_complete"] is False
 assert set(status["missing_fields"]) == {"META_WHATSAPP_APP_SECRET","META_WHATSAPP_WEBHOOK_VERIFY_TOKEN","META_GRAPH_API_VERSION"}
 assert status["customer_credentials_are_workspace_scoped"] is True
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
 ambiguous=src[src.index("except EmailDeliveryFailed"):src.index("return {") ]
 assert 'error_code="delivery_outcome_unknown"' in ambiguous
 assert 'outcome="consumed"' in ambiguous
 assert 'outcome="released"' not in ambiguous



def test_send_route_checks_replayed_quota_reservation_before_claiming_delivery():
 from app.api import delivery_routes
 src=inspect.getsource(delivery_routes.send_delivery)
 guard=src.index('reservation.get("reason") == "idempotent_replay"')
 claim=src.index("store.claim")
 assert guard < claim
 assert 'detail="delivery_send_key_already_used"' in src



def test_delivery_settlement_attempts_quota_even_if_delivery_status_write_raises():
    from app.api import delivery_routes
    src = inspect.getsource(delivery_routes._settle_delivery_attempt)
    delivery_write = src.index("store.finish")
    quota_write = src.index("subscriptions.finish_reservation")
    assert delivery_write < quota_write
    assert "except Exception:" in src
    assert "return delivery_saved, quota_saved" in src


def test_send_route_uses_independent_settlement_for_provider_outcomes():
    from app.api import delivery_routes
    src = inspect.getsource(delivery_routes.send_delivery)
    assert "_settle_delivery_attempt(" in src
    ambiguous = src[src.index("except EmailDeliveryFailed"):src.index("return {\"id\": str(delivery_id)")]
    assert 'error_code="delivery_outcome_unknown"' in ambiguous
    assert 'quota_outcome="consumed"' in ambiguous
    safe_failures = src[:src.index("except EmailDeliveryFailed")]
    assert 'quota_outcome="released"' in safe_failures
    assert 'error_code=None, quota_outcome="consumed"' in src


def test_delivery_settlement_attempts_quota_when_delivery_write_raises():
    import asyncio
    from uuid import uuid4
    from app.api.delivery_routes import _settle_delivery_attempt

    calls = []

    class BrokenDeliveryStore:
        async def finish(self, **kwargs):
            calls.append(("delivery", kwargs["error_code"]))
            raise RuntimeError("database unavailable")

    class QuotaStore:
        async def finish_reservation(self, **kwargs):
            calls.append(("quota", kwargs["outcome"]))
            return True

    result = asyncio.run(_settle_delivery_attempt(
        BrokenDeliveryStore(), QuotaStore(), workspace_id="workspace-a",
        delivery_id=uuid4(), reservation_id=str(uuid4()),
        error_code="delivery_outcome_unknown", quota_outcome="consumed",
    ))

    assert result == (False, True)
    assert calls == [("delivery", "delivery_outcome_unknown"), ("quota", "consumed")]


def test_delivery_settlement_reports_quota_failure_without_undoing_delivery_success():
    import asyncio
    from uuid import uuid4
    from app.api.delivery_routes import _settle_delivery_attempt

    class DeliveryStore:
        async def finish(self, **kwargs):
            return True

    class BrokenQuotaStore:
        async def finish_reservation(self, **kwargs):
            raise RuntimeError("database unavailable")

    result = asyncio.run(_settle_delivery_attempt(
        DeliveryStore(), BrokenQuotaStore(), workspace_id="workspace-a",
        delivery_id=uuid4(), reservation_id=str(uuid4()),
        error_code=None, quota_outcome="consumed",
    ))

    assert result == (True, False)


def test_email_retry_can_recover_a_reserved_preclaim_attempt_without_releasing_winner():
 from app.api import delivery_routes
 due_src=inspect.getsource(delivery_routes.process_due_deliveries)
 send_src=inspect.getsource(delivery_routes.send_delivery)
 assert 'reservation_replayed = reservation.get("reason") == "idempotent_replay"' in due_src
 assert 'reservation.get("status") != "reserved"' in due_src
 assert 'reservation.get("reason") == "idempotent_replay" and data is None' in due_src
 assert 'if not reservation_replayed:' in send_src
 assert 'reservation.get("status") == "consumed"' in send_src


def test_stale_email_delivery_recovery_consumes_matching_reserved_quota_atomically():
 from pathlib import Path
 source=(Path(__file__).resolve().parents[1] / "app" / "services" / "delivery_store.py").read_text(encoding="utf-8")
 start=source.index("    async def reconcile_stale_processing(")
 end=source.index("    @staticmethod",start)
 recovery=source[start:end]
 assert "WITH stale AS" in recovery
 assert "status='uncertain'" in recovery
 assert "UPDATE feature_usage_reservations" in recovery
 assert "'delivery-send:' || m.id::text" in recovery
 assert "r.status='reserved'" in recovery


def test_concurrent_email_claim_loser_never_releases_the_winning_reservation():
 from app.api import delivery_routes
 due_src=inspect.getsource(delivery_routes.process_due_deliveries)
 send_src=inspect.getsource(delivery_routes.send_delivery)
 assert 'str(exc) != "delivery_not_queued"' in due_src
 assert 'str(exc) != "delivery_not_queued"' in send_src

def test_platform_smtp_test_is_owner_only_and_never_sends_email():
 from app.api import platform_admin_routes
 src=inspect.getsource(platform_admin_routes.test_platform_smtp_connection)
 assert 'require_platform_admin(request, write=True)' in src
 assert 'SMTPEmailDelivery().test_connection()' in src
 assert 'send_message' not in src
 assert 'email_sent' in src
 assert any(getattr(route, "path", "") == "/api/v1/platform-admin/smtp/test" for route in platform_admin_routes.router.routes)
 assert not any(getattr(route, "path", "") == "/api/v1/integrations/smtp/test" for route in platform_admin_routes.router.routes)


def test_platform_smtp_status_never_returns_credential_values():
 from types import SimpleNamespace
 from app.api.platform_admin_routes import platform_smtp_status
 cfg=SimpleNamespace(smtp_host="smtp.private.test",smtp_username="private-user",
  smtp_password="private-password",smtp_from_email="noreply@example.test",
  smtp_port=587,smtp_starttls=True)
 status=platform_smtp_status(cfg)
 assert status["configuration_complete"] is True
 assert status["connection_tested"] is False
 assert "private-password" not in repr(status)
 assert "private-user" not in repr(status)
 assert "smtp.private.test" not in repr(status)
 assert "noreply@example.test" not in repr(status)





def test_delivery_enqueue_requires_explicit_workspace_smtp_account_id():
 from pydantic import ValidationError
 with pytest.raises(ValidationError):
  EnqueueDelivery(workspace_id="workspace-a",idempotency_key="send-001-abc")
