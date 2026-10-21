import hmac
import json
import pytest
from pydantic import ValidationError
from app.api.conversation_routes import InboundReply,expected_signature

def valid_payload():
 return {"event_type":"message.received","event_id":"evt-000001","workspace_id":"workspace-a",
  "prospect_id":"00000000-0000-0000-0000-000000000001","provider":"mail-gateway",
  "provider_message_id":"msg-00001","in_reply_to_provider_message_id":"sent-00001",
  "channel":"email","body":"Thanks, please send details.","occurred_at":"2026-10-21T10:00:00Z"}

def test_signed_webhook_signature_is_bound_to_exact_body():
 raw=json.dumps(valid_payload(),separators=(",",":")).encode()
 signature=expected_signature(raw,"s"*40)
 assert hmac.compare_digest(signature,expected_signature(raw,"s"*40))
 assert not hmac.compare_digest(signature,expected_signature(raw+b" ","s"*40))

def test_reply_contract_rejects_extra_fields_and_unknown_channels():
 assert InboundReply.model_validate(valid_payload()).channel=="email"
 with pytest.raises(ValidationError): InboundReply.model_validate({**valid_payload(),"admin":True})
 with pytest.raises(ValidationError): InboundReply.model_validate({**valid_payload(),"channel":"sms"})

def test_reply_contract_rejects_blank_body_wrong_event_and_naive_timestamp():
 with pytest.raises(ValidationError): InboundReply.model_validate({**valid_payload(),"body":"  "})
 with pytest.raises(ValidationError): InboundReply.model_validate({**valid_payload(),"event_type":"message.sent"})
 with pytest.raises(ValidationError): InboundReply.model_validate({**valid_payload(),"occurred_at":"2026-10-21T10:00:00"})
