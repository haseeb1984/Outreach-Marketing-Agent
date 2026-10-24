from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.api.campaign_routes import CampaignCreate, CampaignUpdate, DraftCreate, DraftEdit, DraftReview


def test_campaign_schema_rejects_extra_fields_and_bounds_inputs():
    with pytest.raises(ValidationError):
        CampaignCreate(workspace_id="w", name="n", client_business="b", client_offer="o",
                       target_customer_profile="p", auto_send=True)
    with pytest.raises(ValidationError):
        CampaignCreate(workspace_id="w", name="", client_business="b", client_offer="o",
                       target_customer_profile="p")


def test_draft_schema_limits_channels_and_rejects_client_supplied_body():
    base = dict(workspace_id="w", campaign_id="00000000-0000-0000-0000-000000000001",
                prospect_id="00000000-0000-0000-0000-000000000002", call_to_action="short call?",
                idempotency_key="draft-request-1")
    assert DraftCreate(**base, channel="email").channel == "email"
    with pytest.raises(ValidationError):
        DraftCreate(**base, channel="smtp")
    with pytest.raises(ValidationError):
        DraftCreate(**base, channel="email", body="unverified claims")


def test_review_schema_only_allows_explicit_human_decisions():
    payload = DraftReview(workspace_id="w", decision="approved", note="Reviewed evidence")
    assert payload.decision == "approved"
    with pytest.raises(ValidationError):
        DraftReview(workspace_id="w", decision="send_now")



def test_draft_generation_requires_bounded_idempotency_key():
    base = dict(workspace_id="w", campaign_id="00000000-0000-0000-0000-000000000001",
                prospect_id="00000000-0000-0000-0000-000000000002", call_to_action="short call?",
                channel="email")
    with pytest.raises(ValidationError):
        DraftCreate(**base)
    with pytest.raises(ValidationError):
        DraftCreate(**base, idempotency_key="bad key")
    with pytest.raises(ValidationError):
        DraftCreate(**base, idempotency_key="x" * 181)


def test_draft_route_reserves_quota_before_generation_and_consumes_success():
    import inspect
    from app.api.campaign_routes import create_draft

    source = inspect.getsource(create_draft)
    assert source.index('feature="ai_draft_generations"') < source.index("store.create_draft(")
    assert 'outcome="consumed"' in source
    assert 'outcome="released"' in source
    assert 'reason") == "idempotent_replay"' in source


def test_draft_edit_schema_requires_bounded_body_and_rejects_extra_fields():
    base = {"workspace_id": "workspace-a", "body": "Updated body"}
    assert DraftEdit(**base, subject="Updated subject").body == "Updated body"
    assert DraftEdit(**base, subject="  ").subject is None
    with pytest.raises(ValidationError):
        DraftEdit(workspace_id="workspace-a", body="   ")
    with pytest.raises(ValidationError):
        DraftEdit(**base, auto_send=True)


def test_campaign_update_schema_accepts_lifecycle_states_and_rejects_unknown_status():
    base = {"workspace_id": "workspace-a", "name": "Campaign", "client_business": "Business", "client_offer": "Offer", "target_customer_profile": "Audience"}
    assert CampaignUpdate(**base, status="paused").status == "paused"
    assert CampaignUpdate(**base, status="archived").status == "archived"
    with pytest.raises(ValidationError):
        CampaignUpdate(**base, status="send_now")
