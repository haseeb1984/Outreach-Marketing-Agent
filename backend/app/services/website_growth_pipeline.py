"""End-to-end read-only website discovery and evidence-led growth reporting.

This orchestration authorizes the customer's domain, crawls its public pages,
discovers public competitor candidates, compares bounded page evidence, and
composes a reviewable SEO plan. It never changes the customer's website or
sends outreach.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlunsplit

from app.core.config import settings
from app.services.competitor_page_analysis import analyze_competitor_pages
from app.services.competitor_research import discover_competitor_candidates
from app.services.website_discovery import discover_and_crawl
from app.services.website_growth_report import build_website_growth_report
from app.services.website_fetch import FetchLimits, Resolver
from app.services.domain_authorization import authorize_domain_url


async def discover_and_build_growth_report(
    start_url: str,
    *,
    business_type: str,
    target_market: str,
    target_queries: list[str],
    competitor_sources: list[str] | None = None,
    workspace_id: str,
    verified_domains: list[dict[str, Any]],
    competitor_gaps: list[dict[str, Any]] | None = None,
    max_pages: int = 25,
    max_depth: int = 2,
    max_sitemaps: int = 3,
    limits: FetchLimits = FetchLimits(),
    resolver: Resolver | None = None,
) -> dict[str, Any]:
    """Authorize the workspace domain before any network fetch, then build a report."""
    authorization = authorize_domain_url(start_url, workspace_id, verified_domains)
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
            "domain_authorization": {
                "workspace_id": authorization["workspace_id"],
                "host": authorization["host"],
                "verified_domain_required": True,
            },
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

    crawl_report = discovery["crawl"]
    competitor_discovery: dict[str, Any] = {
        "status": "skipped",
        "reason": "target_queries_not_configured",
        "items": [],
        "count": 0,
    }
    competitor_analysis: dict[str, Any] = {
        "status": "skipped",
        "reason": "target_queries_not_configured",
        "items": [],
        "potential_gaps": [],
        "pages_checked": 0,
        "pages_analyzed": 0,
    }
    effective_gaps = list(competitor_gaps or [])
    supplied_competitors = list(dict.fromkeys(item.strip() for item in (competitor_sources or []) if isinstance(item, str) and item.strip()))[:20]

    # Competitor intelligence is part of the actual growth workflow, not a
    # separate dormant service. Search candidates remain explicitly unconfirmed;
    # comparison is limited to three public pages and the pages crawled above.
    queries = list(dict.fromkeys(
        query.strip() for query in target_queries
        if isinstance(query, str) and query.strip()
    ))[:3]
    if queries:
        competitor_discovery = await discover_competitor_candidates(
            website_url=start_url,
            target_queries=queries,
            api_key=settings.brave_search_api_key,
            max_candidates=12,
        )

        candidates = list(competitor_discovery.get("items", []))
        # Explicit HTTPS URLs saved on the project are compared alongside search candidates.
        from urllib.parse import urlsplit
        own_host = (urlsplit(start_url).hostname or "").lower().rstrip(".")
        for source in supplied_competitors:
            parsed = urlsplit(source)
            if (parsed.scheme.lower() == "https" and parsed.hostname
                    and parsed.username is None and parsed.password is None
                    and parsed.port in (None, 443)):
                host = parsed.hostname.lower().rstrip(".")
                if host != own_host and not host.endswith("." + own_host):
                    candidates.insert(0, {
                        "domain": host, "title": "Customer-supplied competitor source",
                        "url": urlunsplit(("https", parsed.netloc, parsed.path or "/", "", "")), "description": "", "matched_queries": [],
                        "relevance_score": 100.0, "evidence_type": "customer_supplied_source",
                        "competitor_status": "candidate_requires_human_review",
                        "requires_human_review": True,
                    })

        if candidates:
            competitor_analysis = await analyze_competitor_pages(
                candidates=candidates,
                target_queries=queries,
                client_pages=crawl_report.get("pages", []),
                resolver=resolver,
                max_candidates=3,
            )
            effective_gaps.extend(
                item for item in competitor_analysis.get("potential_gaps", [])
                if isinstance(item, dict)
            )
        elif competitor_discovery.get("status") != "completed":
            competitor_analysis = {
                "status": "unavailable",
                "reason": competitor_discovery.get("reason", "competitor_discovery_unavailable"),
                "items": [],
                "potential_gaps": [],
                "pages_checked": 0,
                "pages_analyzed": 0,
                "notice": "Competitor page comparison was skipped because candidate discovery was unavailable.",
            }

    report = build_website_growth_report(
        crawl_report=crawl_report,
        business_type=business_type,
        target_market=target_market,
        target_queries=queries,
        competitor_gaps=effective_gaps,
    )
    report["status"] = "report_ready_for_human_review"
    report["domain_authorization"] = {
        "workspace_id": authorization["workspace_id"],
        "host": authorization["host"],
        "verified_domain_required": True,
    }
    report["discovery"] = {
        "robots": discovery.get("robots"),
        "sitemap_documents": discovery.get("sitemap_documents", []),
        "sitemap_seed_urls_discovered": discovery.get("sitemap_seed_urls_discovered", 0),
    }
    competitor_discovery["customer_supplied_hints"] = supplied_competitors
    report["competitor_discovery"] = competitor_discovery
    report["competitor_analysis"] = competitor_analysis
    report["limitations"] = list(dict.fromkeys([
        *report.get("limitations", []),
        *discovery.get("limitations", []),
        "Competitor candidates, including customer-supplied sources, are unconfirmed leads and require human review.",
        "Competitor comparisons cover at most three public pages and the bounded client crawl; gaps require human review.",
    ]))
    return report
