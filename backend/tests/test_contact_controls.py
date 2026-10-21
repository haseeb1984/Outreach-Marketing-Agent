import pytest
from pydantic import ValidationError
from app.api.campaign_routes import ContactControlUpdate, DraftCreate


def test_contact_control_requires_https_evidence():
    with pytest.raises(ValidationError):
        ContactControlUpdate(workspace_id="w", whatsapp_opt_in_confirmed=True, whatsapp_opt_in_evidence_url="http://example.com/proof")
    with pytest.raises(ValidationError):
        ContactControlUpdate(workspace_id="w", whatsapp_opt_in_confirmed=True, whatsapp_opt_in_evidence_url="https://user:pass@example.com/proof")


def test_draft_request_cannot_claim_consent():
    with pytest.raises(ValidationError):
        DraftCreate(workspace_id="w", campaign_id="00000000-0000-0000-0000-000000000001", prospect_id="00000000-0000-0000-0000-000000000002", channel="whatsapp", call_to_action="Discuss?", whatsapp_opt_in_confirmed=True)


def test_contact_controls_reject_extra_fields():
    with pytest.raises(ValidationError):
        ContactControlUpdate(workspace_id="w", send_now=True)
