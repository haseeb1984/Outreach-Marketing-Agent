import asyncio

import pytest

from app.services import website_growth_pipeline


def test_pipeline_composes_discovery_crawl_and_growth_report(monkeypatch):
    async def fake_discover(start_url, **kwargs):
        return {
            "start_url": start_url,
            "crawl_skipped": False,
            "robots": {"status": "available"},
            "sitemap_documents": [{"url": "https://client.example/sitemap.xml"}],
            "sitemap_seed_urls_discovered": 1,
            "crawl": {
                "start_url": start_url,
                "pages_crawled": 1,
                "aggregate_findings": [{
                    "code": "missing_title",
                    "title": "Missing title",
                    "severity": "medium",
                    "occurrences": 1,
                    "evidence_urls": ["https://client.example/"],
                }],
                "limitations": ["Source HTML only."],
            },
            "limitations": ["Bounded discovery."],
        }

    monkeypatch.setattr(website_growth_pipeline, "discover_and_crawl", fake_discover)
    result = asyncio.run(website_growth_pipeline.discover_and_build_growth_report(
        "https://client.example/",
        business_type="local service",
        target_market="Karachi",
        workspace_id="workspace-1",
        verified_domains=[{"domain": "client.example", "workspace_id": "workspace-1", "status": "verified"}],
        target_queries=["service Karachi"],
    ))
    assert result["status"] == "report_ready_for_human_review"
    assert result["discovery"]["sitemap_seed_urls_discovered"] == 1
    assert result["strategy"]["actions"][0]["evidence_url"] == "https://client.example/"
    assert "Bounded discovery." in result["limitations"]


def test_pipeline_does_not_generate_actions_when_discovery_fails_closed(monkeypatch):
    async def fake_discover(start_url, **kwargs):
        return {
            "start_url": start_url,
            "crawl_skipped": True,
            "reason": "robots_txt_unavailable_fail_closed",
            "robots": {"error": "unsafe resolution"},
            "sitemap_documents": [],
            "crawl": None,
            "limitations": ["Crawl was skipped."],
        }

    def forbidden_report(**kwargs):
        raise AssertionError("growth strategy must not run without crawl evidence")

    monkeypatch.setattr(website_growth_pipeline, "discover_and_crawl", fake_discover)
    monkeypatch.setattr(website_growth_pipeline, "build_website_growth_report", forbidden_report)
    result = asyncio.run(website_growth_pipeline.discover_and_build_growth_report(
        "https://client.example/",
        business_type="SaaS",
        target_market="Global",
        target_queries=["software"],
        workspace_id="workspace-1",
        verified_domains=[{"domain": "client.example", "workspace_id": "workspace-1", "status": "verified"}],
    ))
    assert result["status"] == "crawl_skipped"
    assert result["strategy"]["actions"] == []
    assert result["reason"] == "robots_txt_unavailable_fail_closed"

def test_pipeline_rejects_unverified_or_cross_workspace_domain_before_fetch(monkeypatch):
    async def forbidden_discover(*args, **kwargs):
        raise AssertionError("discovery must not run before domain authorization")

    monkeypatch.setattr(website_growth_pipeline, "discover_and_crawl", forbidden_discover)
    for workspace_id, records in (
        ("workspace-1", []),
        ("workspace-2", [{"domain": "client.example", "workspace_id": "workspace-1", "status": "verified"}]),
    ):
        try:
            asyncio.run(website_growth_pipeline.discover_and_build_growth_report(
                "https://client.example/",
                workspace_id=workspace_id,
                verified_domains=records,
                business_type="SaaS",
                target_market="Global",
                target_queries=["software"],
            ))
        except PermissionError:
            pass
        else:
            raise AssertionError("unauthorized domain should be rejected")


def test_growth_review_request_requires_bounded_queries_and_rejects_extra_fields():
    from uuid import uuid4
    from pydantic import ValidationError
    from app.api.website_audit_routes import WebsiteGrowthReviewRequest

    base = {
        "workspace_id": "workspace-a",
        "project_id": uuid4(),
        "target_queries": ["local plumber", "emergency plumber"],
        "idempotency_key": "growth-review-123",
    }
    payload = WebsiteGrowthReviewRequest(**base)
    assert payload.target_queries == ["local plumber", "emergency plumber"]
    with pytest.raises(ValidationError):
        WebsiteGrowthReviewRequest(**{**base, "target_queries": ["  ", ""]})
    with pytest.raises(ValidationError):
        WebsiteGrowthReviewRequest(**{**base, "target_queries": ["x" * 201]})
    with pytest.raises(ValidationError):
        WebsiteGrowthReviewRequest(**{**base, "auto_publish": True})
