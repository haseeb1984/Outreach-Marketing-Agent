from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.api.campaign_routes import CampaignCreate, DraftCreate, DraftReview


def test_campaign_schema_rejects_extra_fields_and_bounds_inputs():
    with pytest.raises(ValidationError):
        CampaignCreate(workspace_id="w", name="n", client_business="b", client_offer="o",
                       target_customer_profile="p", auto_send=True)
    with pytest.raises(ValidationError):
        CampaignCreate(workspace_id="w", name="", client_business="b", client_offer="o",
                       target_customer_profile="p")


def test_draft_schema_limits_channels_and_rejects_client_supplied_body():
    base = dict(workspace_id="w", campaign_id="00000000-0000-0000-0000-000000000001",
                prospect_id="00000000-0000-0000-0000-000000000002", call_to_action="short call?")
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
