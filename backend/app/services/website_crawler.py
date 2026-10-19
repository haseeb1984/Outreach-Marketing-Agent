"""Bounded, read-only same-host website crawler built on the safe fetch and audit services.

This module is not an authenticated production endpoint. A deployment serving
untrusted tenants still needs connection-pinned egress, tenant authorization,
quotas, queueing, and abuse controls.
"""
from __future__ import annotations

import asyncio
from collections import deque
from urllib.parse import urlsplit, urlunsplit

from app.services.website_audit import analyze_html, validate_page_url
from app.services.website_fetch import FetchLimits, Resolver, fetch_html
from app.services.robots_sitemap import evaluate_robots_path


def _normalize_crawl_url(value: str) -> str:
    """Validate a crawl URL and remove fragments, which are not server resources."""
    valid = validate_page_url(value)
    parts = urlsplit(valid)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".")


async def crawl_website(
    start_url: str,
    *,
    max_pages: int = 25,
    max_depth: int = 2,
    limits: FetchLimits = FetchLimits(),
    resolver: Resolver | None = None,
    robots_txt: str | None = None,
    user_agent: str = "OutreachMarketingAgentAudit",
) -> dict:
    """Crawl a bounded number of same-host pages and aggregate deterministic findings.

    Redirects outside the original host are recorded and never followed further by
    this crawler. Every page fetch still goes through the bounded fetch service.
    """
    if not 1 <= max_pages <= 100:
        raise ValueError("max_pages must be between 1 and 100")
    if not 0 <= max_depth <= 5:
        raise ValueError("max_depth must be between 0 and 5")

    start = _normalize_crawl_url(start_url)
    allowed_host = _host(start)
    queue = deque([(start, 0)])
    queued = {start}
    visited: set[str] = set()
    pages: list[dict] = []
    errors: list[dict] = []
    cross_host_redirects: list[dict] = []
    robots_blocked: list[dict] = []
    findings_by_code: dict[str, dict] = {}

    while queue and len(pages) < max_pages:
        requested, depth = queue.popleft()
        if requested in visited:
            continue
        visited.add(requested)
        if robots_txt is not None:
            parts = urlsplit(requested)
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            decision = evaluate_robots_path(body=robots_txt, path=path, user_agent=user_agent)
            if not decision["allowed"]:
                robots_blocked.append({
                    "url": requested,
                    "matched_rule": decision["matched_rule"],
                    "action": "skipped_due_to_robots_txt",
                })
                continue
        kwargs = {"limits": limits, "allowed_hosts": {allowed_host}}
        if resolver is not None:
            kwargs["resolver"] = resolver
        try:
            fetched = await fetch_html(requested, **kwargs)
        except (ValueError, OSError) as exc:
            if "outside the allowed host scope" in str(exc):
                cross_host_redirects.append({
                    "requested_url": requested,
                    "action": "redirect_blocked_before_request",
                    "reason": str(exc),
                })
            else:
                errors.append({"url": requested, "depth": depth, "error": str(exc)})
            continue

        final_url = _normalize_crawl_url(fetched.final_url)
        if _host(final_url) != allowed_host:
            cross_host_redirects.append({
                "requested_url": requested,
                "redirected_to": final_url,
                "action": "not_crawled_outside_start_host",
            })
            continue

        report = analyze_html(page_url=final_url, html=fetched.body, status_code=fetched.status_code)
        page_entry = {
            "requested_url": requested,
            "final_url": final_url,
            "depth": depth,
            "status_code": fetched.status_code,
            "title": report["observations"]["title"],
            "internal_links_count": len(report["observations"]["internal_links"]),
            "findings": report["findings"],
        }
        pages.append(page_entry)
        for finding in report["findings"]:
            code = finding["code"]
            if code not in findings_by_code:
                findings_by_code[code] = {
                    "code": code,
                    "title": finding["title"],
                    "severity": finding["severity"],
                    "occurrences": 0,
                    "evidence_urls": [],
                }
            aggregate = findings_by_code[code]
            aggregate["occurrences"] += 1
            if final_url not in aggregate["evidence_urls"]:
                aggregate["evidence_urls"].append(final_url)

        if depth >= max_depth:
            continue
        for link in report["observations"]["internal_links"]:
            try:
                candidate = _normalize_crawl_url(link["url"])
            except ValueError:
                continue
            if _host(candidate) != allowed_host or candidate in queued or candidate in visited:
                continue
            queued.add(candidate)
            queue.append((candidate, depth + 1))
            if len(queued) >= max_pages * 10:
                # Keep the discovered frontier bounded even on link-heavy pages.
                break

    return {
        "start_url": start,
        "scope": {"host": allowed_host, "max_pages": max_pages, "max_depth": max_depth},
        "pages_crawled": len(pages),
        "pages": pages,
        "errors": errors,
        "cross_host_redirects_not_crawled": cross_host_redirects,
        "robots_blocked_pages": robots_blocked,
        "aggregate_findings": sorted(
            findings_by_code.values(),
            key=lambda item: (-item["occurrences"], item["code"]),
        ),
        "limitations": [
            "Robots rules are enforced only when robots_txt is supplied by a trusted bounded retrieval layer; this crawler does not fetch robots.txt itself.",
            "This is a bounded source-HTML crawl, not a JavaScript-rendered, accessibility, performance, or search-index audit.",
            "DNS is checked before each request, but production multi-tenant use still requires connection-pinned egress to eliminate DNS-rebinding races.",
            "The crawler is not exposed as an API endpoint; authentication, workspace authorization, quotas, and abuse controls are required first.",
        ],
    }
