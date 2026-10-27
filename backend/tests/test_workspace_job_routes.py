import pytest
from pydantic import ValidationError

from app.api.workspace_job_routes import WebsiteGrowthScanRequest, _normalize_start_url


def test_growth_scan_request_normalizes_url_and_deduplicates_queries():
    payload = WebsiteGrowthScanRequest(
        workspace_id="workspace-a",
        start_url="https://example.com/growth?token=do-not-store#section",
        business_type="  SaaS  ",
        target_market="  United States  ",
        target_queries=[" CRM software ", "CRM software", "marketing automation"],
    )

    assert payload.start_url == "https://example.com/growth"
    assert payload.business_type == "SaaS"
    assert payload.target_market == "United States"
    assert payload.target_queries == ["CRM software", "marketing automation"]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:password@example.com/",
        "https://example.com:8443/",
        "javascript:alert(1)",
        "https:///missing-host",
    ],
)
def test_growth_scan_rejects_unsafe_website_urls(url):
    with pytest.raises((ValueError, ValidationError)):
        _normalize_start_url(url)


def test_growth_scan_requires_workspace_and_bounded_inputs():
    with pytest.raises(ValidationError):
        WebsiteGrowthScanRequest(
            workspace_id="",
            start_url="https://example.com",
            business_type="SaaS",
            target_market="US",
            max_pages=11,
        )


def test_growth_scan_does_not_accept_boolean_page_limits():
    with pytest.raises(ValidationError):
        WebsiteGrowthScanRequest(
            workspace_id="workspace-a",
            start_url="https://example.com",
            business_type="SaaS",
            target_market="US",
            max_pages=True,
        )


def test_growth_scan_rejects_empty_queries():
    with pytest.raises(ValidationError):
        WebsiteGrowthScanRequest(
            workspace_id="workspace-a",
            start_url="https://example.com",
            business_type="SaaS",
            target_market="US",
            target_queries=["valid query", "   "],
        )
