"""Compose crawl observations into an evidence-led website growth report.

This is a pure composition layer: it does not fetch pages, modify client sites,
send outreach, or promise search-ranking outcomes.
"""
from __future__ import annotations

from typing import Any

from app.services.seo_strategy import build_seo_strategy


def build_website_growth_report(
    *,
    crawl_report: dict[str, Any],
    business_type: str,
    target_market: str,
    target_queries: list[str],
    competitor_gaps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Combine bounded crawler output and business context into one reviewable plan."""
    start_url = str(crawl_report.get("start_url", "")).strip()
    if not start_url:
        raise ValueError("crawl_report must include start_url")

    aggregated = crawl_report.get("aggregate_findings", [])
    if not isinstance(aggregated, list):
        raise ValueError("crawl_report aggregate_findings must be a list")

    strategy_findings: list[dict[str, Any]] = []
    for finding in aggregated:
        if not isinstance(finding, dict):
            continue
        evidence_urls = finding.get("evidence_urls", [])
        if not isinstance(evidence_urls, list) or not evidence_urls:
            # No evidence URL means no recommendation is generated.
            continue
        evidence_url = str(evidence_urls[0]).strip()
        if not evidence_url:
            continue
        occurrences = finding.get("occurrences", 1)
        try:
            affected_pages = max(1, min(int(occurrences), 10_000))
        except (TypeError, ValueError):
            affected_pages = 1
        severity_map = {"high": 5, "medium": 3, "low": 2}
        strategy_findings.append({
            "id": str(finding.get("code") or "crawl-finding"),
            "category": str(finding.get("category") or "technical_seo"),
            "title": str(finding.get("title") or "").strip(),
            "evidence_url": evidence_url,
            "severity": severity_map.get(str(finding.get("severity", "")).lower(), 2),
            "affected_pages": affected_pages,
            "business_relevance": 3,
            "recommended_action": (
                "Review the cited page evidence, confirm whether the condition is intentional, "
                "and make a change only after approval."
            ),
        })

    strategy = build_seo_strategy(
        business_type=business_type,
        target_market=target_market,
        target_queries=target_queries,
        site_findings=strategy_findings,
        competitor_gaps=competitor_gaps,
    )
    return {
        "report_type": "website_growth_review",
        "start_url": start_url,
        "crawl_summary": {
            "pages_crawled": crawl_report.get("pages_crawled", 0),
            "scope": crawl_report.get("scope", {}),
            "errors": crawl_report.get("errors", []),
            "cross_host_redirects_not_crawled": crawl_report.get("cross_host_redirects_not_crawled", []),
        },
        "strategy": strategy,
        "review_required": True,
        "limitations": [
            "Recommendations are derived only from supplied crawl findings and competitor evidence.",
            "Occurrence counts are counts of observed pages, not proof of traffic impact or ranking loss.",
            "No client site is changed and no outreach is sent by this report builder.",
            *crawl_report.get("limitations", []),
        ],
    }
