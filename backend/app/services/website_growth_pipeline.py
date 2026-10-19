"""End-to-end read-only website discovery and growth-report composition.

This orchestration does not expose a public endpoint, mutate client websites,
send outreach, or guarantee search-ranking outcomes.
"""
from __future__ import annotations

from typing import Any

from app.services.website_discovery import discover_and_crawl
from app.services.website_growth_report import build_website_growth_report
from app.services.website_fetch import FetchLimits, Resolver


async def discover_and_build_growth_report(
    start_url: str,
    *,
    business_type: str,
    target_market: str,
    target_queries: list[str],
    competitor_gaps: list[dict[str, Any]] | None = None,
    max_pages: int = 25,
    max_depth: int = 2,
    max_sitemaps: int = 3,
    limits: FetchLimits = FetchLimits(),
    resolver: Resolver | None = None,
) -> dict[str, Any]:
    """Discover crawl inputs, run a bounded crawl, and build a reviewable report."""
    discovery = await discover_and_crawl(
        start_url,
        max_pages=max_pages,
        max_depth=max_depth,
        max_sitemaps=max_sitemaps,
        limits=limits,
        resolver=resolver,
    )

    if discovery.get("crawl_skipped") is True or not isinstance(discovery.get("crawl"), dict):
        return {
            "report_type": "website_growth_review",
            "start_url": discovery.get("start_url", start_url),
            "status": "crawl_skipped",
            "reason": discovery.get("reason", "crawl_report_unavailable"),
            "discovery": {
                "robots": discovery.get("robots"),
                "sitemap_documents": discovery.get("sitemap_documents", []),
                "sitemap_seed_urls_discovered": discovery.get("sitemap_seed_urls_discovered", 0),
            },
            "crawl_summary": None,
            "strategy": {
                "actions": [],
                "status": "not_generated_without_crawl_evidence",
            },
            "review_required": True,
            "limitations": [
                "No SEO actions were generated because a safe crawl report was unavailable.",
                "No client website was changed and no outreach was sent.",
                *discovery.get("limitations", []),
            ],
        }

    report = build_website_growth_report(
        crawl_report=discovery["crawl"],
        business_type=business_type,
        target_market=target_market,
        target_queries=target_queries,
        competitor_gaps=competitor_gaps,
    )
    report["status"] = "report_ready_for_human_review"
    report["discovery"] = {
        "robots": discovery.get("robots"),
        "sitemap_documents": discovery.get("sitemap_documents", []),
        "sitemap_seed_urls_discovered": discovery.get("sitemap_seed_urls_discovered", 0),
    }
    report["limitations"] = list(dict.fromkeys([
        *report.get("limitations", []),
        *discovery.get("limitations", []),
    ]))
    return report
