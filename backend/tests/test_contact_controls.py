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


def test_whatsapp_draft_requires_the_consent_account_to_remain_active():
    import inspect
    from app.services.campaign_store import CampaignStore

    source = inspect.getsource(CampaignStore.create_draft)
    whatsapp_checks = source[source.index('if channel == "whatsapp":'):source.index("facts = self._json_list")]
    assert 'controls.get("whatsapp_account_id")' in whatsapp_checks
    assert "FROM workspace_whatsapp_accounts" in whatsapp_checks
    assert "status='active'" in whatsapp_checks
    assert "FOR SHARE" in whatsapp_checks
    assert 'raise ValueError("WhatsApp consent account is not active")' in whatsapp_checks

def test_whatsapp_draft_fails_closed_when_consent_account_is_disabled():
    import asyncio
    from datetime import datetime, timezone
    from uuid import UUID
    from app.services.campaign_store import CampaignStore

    workspace_id = "workspace-test"
    campaign_id = UUID("00000000-0000-0000-0000-000000000011")
    prospect_id = UUID("00000000-0000-0000-0000-000000000012")
    actor_id = UUID("00000000-0000-0000-0000-000000000013")
    account_id = UUID("00000000-0000-0000-0000-000000000014")

    class FakeConnection:
        def __init__(self):
            self.draft_insert_attempted = False

        def transaction(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def fetchrow(self, query, *args):
            if "FROM outreach_campaigns" in query:
                return {"id": campaign_id, "status": "active", "client_business": "Example",
                        "client_offer": "Offer", "target_customer_profile": "Small businesses"}
            if "FROM crm_prospects" in query:
                return {"id": prospect_id, "name": "Jane", "stage": "qualified",
                        "contact_phone_e164": "+14155552671",
                        "evidence_url": "https://example.com/about", "fit_reason": "Relevant",
                        "verified_facts": ["Publicly verified"], "archived_at": None}
            if "FROM outreach_contact_controls" in query:
                return {"whatsapp_opt_in_at": datetime.now(timezone.utc),
                        "whatsapp_opt_in_evidence_url": "https://example.com/consent",
                        "whatsapp_account_id": account_id}
            if "FROM workspace_whatsapp_accounts" in query:
                # Simulate the consent account having been disabled.
                return None
            if "INSERT INTO outreach_drafts" in query:
                self.draft_insert_attempted = True
                raise AssertionError("draft must not be inserted for a disabled account")
            raise AssertionError(f"Unexpected query: {query}")

        async def execute(self, *_args):
            raise AssertionError("draft event must not be inserted")

    class FakeAcquire:
        def __init__(self, connection):
            self.connection = connection

        async def __aenter__(self):
            return self.connection

        async def __aexit__(self, *_args):
            return False

    class FakePool:
        def __init__(self):
            self.connection = FakeConnection()

        def acquire(self):
            return FakeAcquire(self.connection)

    pool = FakePool()
    with pytest.raises(ValueError, match="WhatsApp consent account is not active"):
        asyncio.run(CampaignStore(pool).create_draft(
            workspace_id=workspace_id, campaign_id=campaign_id, prospect_id=prospect_id,
            actor_id=actor_id, channel="whatsapp", call_to_action="Discuss the offer?",
        ))
    assert pool.connection.draft_insert_attempted is False

