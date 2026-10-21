import pytest

from app.services.website_growth_report import build_website_growth_report


def test_growth_report_turns_crawl_findings_into_evidence_backed_actions():
    crawl = {
        "start_url": "https://client.example/",
        "pages_crawled": 3,
        "scope": {"host": "client.example", "max_pages": 10, "max_depth": 2},
        "aggregate_findings": [
            {
                "code": "missing_title",
                "title": "Missing or empty title element",
                "severity": "medium",
                "occurrences": 2,
                "evidence_urls": ["https://client.example/services"],
            },
            {
                "code": "unverified",
                "title": "No evidence finding",
                "severity": "high",
                "occurrences": 1,
                "evidence_urls": [],
            },
        ],
        "errors": [],
        "cross_host_redirects_not_crawled": [],
        "limitations": ["Test crawler limitation."],
    }
    result = build_website_growth_report(
        crawl_report=crawl,
        business_type="local service business",
        target_market="Karachi",
        target_queries=["service provider Karachi"],
    )

    assert result["report_type"] == "website_growth_review"
    assert result["review_required"] is True
    assert result["crawl_summary"]["pages_crawled"] == 3
    assert len(result["strategy"]["actions"]) == 1
    action = result["strategy"]["actions"][0]
    assert action["evidence_url"] == "https://client.example/services"
    assert action["source"] == "site_observation"
    assert result["strategy"]["method"]["ranking_guarantee"] is False
    assert "Test crawler limitation." in result["limitations"]


def test_growth_report_includes_competitor_gap_only_with_evidence():
    result = build_website_growth_report(
        crawl_report={"start_url": "https://client.example/", "aggregate_findings": []},
        business_type="SaaS",
        target_market="Global",
        target_queries=["project management software"],
        competitor_gaps=[
            {"gap": "Competitor has a public integration guide", "evidence_url": "https://competitor.example/integrations"},
            {"gap": "Unverified competitor claim"},
        ],
    )
    assert len(result["strategy"]["actions"]) == 1
    assert result["strategy"]["actions"][0]["source"] == "observed_competitor_gap"


def test_growth_report_rejects_missing_start_url_or_invalid_findings():
    with pytest.raises(ValueError):
        build_website_growth_report(
            crawl_report={}, business_type="SaaS", target_market="Global", target_queries=["x"]
        )
    with pytest.raises(ValueError):
        build_website_growth_report(
            crawl_report={"start_url": "https://client.example/", "aggregate_findings": {}},
            business_type="SaaS", target_market="Global", target_queries=["x"]
        )



@pytest.mark.parametrize("evidence_url", [
    "https://other.example/page",
    "https://user:secret@client.example/page",
    "https://client.example/page?access_token=secret",
    "https://client.example/page#private-fragment",
    "https://client.example:99999/page",
    "javascript:alert(1)",
])
def test_growth_report_does_not_emit_untrusted_evidence_urls(evidence_url):
    result = build_website_growth_report(
        crawl_report={
            "start_url": "https://client.example/",
            "aggregate_findings": [{
                "code": "injected_finding",
                "title": "Untrusted supplied finding",
                "severity": "high",
                "evidence_urls": [evidence_url],
            }],
        },
        business_type="SaaS",
        target_market="Global",
        target_queries=["workflow software"],
    )
    assert result["strategy"]["actions"] == []


@pytest.mark.parametrize("start_url", [
    "",
    "javascript:alert(1)",
    "https://user:secret@client.example/",
    "https://client.example:99999/",
    "https://client.example/path with spaces",
])
def test_growth_report_rejects_invalid_start_url(start_url):
    with pytest.raises(ValueError, match="valid HTTP"):
        build_website_growth_report(
            crawl_report={"start_url": start_url, "aggregate_findings": []},
            business_type="SaaS",
            target_market="Global",
            target_queries=["workflow software"],
        )
