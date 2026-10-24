import pytest
from pydantic import ValidationError
from app.api.campaign_routes import DraftCreate
from app.api.prospect_routes import ContactControlsUpdate


def test_contact_control_requires_https_evidence():
    with pytest.raises(ValidationError):
        ContactControlsUpdate(workspace_id="w", whatsapp_opt_in_confirmed=True, whatsapp_opt_in_evidence_url="http://example.com/proof")
    with pytest.raises(ValidationError):
        ContactControlsUpdate(workspace_id="w", whatsapp_opt_in_confirmed=True, whatsapp_opt_in_evidence_url="https://user:pass@example.com/proof")


def test_draft_request_cannot_claim_consent():
    with pytest.raises(ValidationError):
        DraftCreate(workspace_id="w", campaign_id="00000000-0000-0000-0000-000000000001", prospect_id="00000000-0000-0000-0000-000000000002", channel="whatsapp", call_to_action="Discuss?", whatsapp_opt_in_confirmed=True)


def test_contact_controls_reject_extra_fields():
    with pytest.raises(ValidationError):
        ContactControlsUpdate(workspace_id="w", send_now=True)



def test_contact_controls_require_whatsapp_account_for_documented_opt_in():
    from uuid import UUID
    from app.api.prospect_routes import update_contact_controls
    import inspect

    source = inspect.getsource(update_contact_controls)
    assert "whatsapp_account_required_for_consent" in source
    assert "whatsapp_account_id=payload.whatsapp_account_id" in source
    payload = ContactControlsUpdate(
        workspace_id="w",
        whatsapp_opt_in_confirmed=True,
        whatsapp_account_id=UUID("00000000-0000-0000-0000-000000000001"),
        whatsapp_opt_in_evidence_url="https://example.com/consent-proof",
    )
    assert payload.whatsapp_account_id is not None


def test_contact_controls_route_passes_account_id_to_persistence():
    import inspect
    from app.api.prospect_routes import update_contact_controls

    source = inspect.getsource(update_contact_controls)
    assert "whatsapp_account_id=payload.whatsapp_account_id" in source
    assert "whatsapp_account_required_for_consent" in source
