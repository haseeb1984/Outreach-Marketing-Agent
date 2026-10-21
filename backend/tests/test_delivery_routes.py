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
