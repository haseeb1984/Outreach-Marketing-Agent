import pytest
from pydantic import ValidationError

from app.api.workspace_growth_schedule_routes import (
    GrowthScheduleCreate,
    GrowthScheduleStatusUpdate,
)


def test_growth_schedule_bounds_interval_and_normalizes_payload():
    payload = GrowthScheduleCreate(
        workspace_id="workspace-a",
        start_url="https://example.com/?token=secret",
        business_type=" SaaS ",
        target_market=" US ",
        target_queries=[" automation ", "automation"],
        interval_hours=24,
    )
    assert payload.start_url == "https://example.com/"
    assert payload.business_type == "SaaS"
    assert payload.target_market == "US"
    assert payload.target_queries == ["automation"]
    assert payload.interval_hours == 24


@pytest.mark.parametrize("interval", [1, 5, 721, True])
def test_growth_schedule_rejects_out_of_range_or_boolean_interval(interval):
    with pytest.raises(ValidationError):
        GrowthScheduleCreate(
            workspace_id="workspace-a",
            start_url="https://example.com/",
            business_type="SaaS",
            target_market="US",
            interval_hours=interval,
        )


def test_growth_schedule_rejects_non_https_and_extra_fields():
    with pytest.raises(ValidationError):
        GrowthScheduleCreate(
            workspace_id="workspace-a",
            start_url="http://example.com/",
            business_type="SaaS",
            target_market="US",
        )
    with pytest.raises(ValidationError):
        GrowthScheduleCreate(
            workspace_id="workspace-a",
            start_url="https://example.com/",
            business_type="SaaS",
            target_market="US",
            arbitrary_field="not-allowed",
        )


@pytest.mark.parametrize("status", ["running", "deleted", "", "ACTIVE"])
def test_schedule_status_only_allows_active_or_paused(status):
    with pytest.raises(ValidationError):
        GrowthScheduleStatusUpdate(workspace_id="workspace-a", status=status)
