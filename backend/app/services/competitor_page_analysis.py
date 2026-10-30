"""Evidence-based competitor page comparison for bounded SEO growth reviews.

Search candidates are fetched only over public HTTPS through the shared SSRF-safe
fetch layer. Robots rules are checked before competitor page retrieval. Findings
are scoped to the pages actually crawled and never presented as site-wide proof.
"""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.services.robots_sitemap import evaluate_robots_path
from app.services.website_audit import analyze_html, validate_page_url
from app.services.website_fetch import FetchLimits, Resolver, fetch_html, fetch_text_document


_STOP_WORDS = {
    "about", "after", "best", "from", "into", "near", "that", "their", "these",
    "this", "with", "your", "what", "when", "where", "which", "will", "for",
    "the", "and", "are", "how", "our", "you", "all", "can",
}


def _terms(value: str) -> set[str]:
    import re
    return {
        word.lower() for word in re.findall(r"[a-z0-9]{3,}", value.lower())
        if word.lower() not in _STOP_WORDS
    }


def _page_text(page: dict[str, Any]) -> str:
    headings = page.get("headings") or {}
    heading_text = " ".join(
        str(value) for values in headings.values() if isinstance(values, list)
        for value in values
    )
    descriptions = page.get("meta_descriptions") or []
    return " ".join([
        str(page.get("title") or ""),
        " ".join(str(value) for value in descriptions),
        heading_text,
    ])


def _host(url: str) -> str:
    parsed = urlsplit(validate_page_url(url))
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.port not in (None, 443):
        raise ValueError("competitor_page_must_use_public_https")
    return parsed.hostname.lower().rstrip(".")


def _coverage(query: str, text: str) -> tuple[float, list[str]]:
    wanted = _terms(query)
    if not wanted:
        return 0.0, []
    found = sorted(wanted & _terms(text))
    return round(len(found) / len(wanted), 3), found


async def analyze_competitor_pages(
    *,
    candidates: list[dict[str, Any]],
    target_queries: list[str],
    client_pages: list[dict[str, Any]],
    client: httpx.AsyncClient | None = None,
    resolver: Resolver | None = None,
    max_candidates: int = 3,
) -> dict[str, Any]:
    """Fetch up to three candidate pages and compare title/meta/headings to client crawl evidence."""
    own_text = " ".join(_page_text(page) for page in client_pages if isinstance(page, dict))
    own_urls = [
        str(page.get("url") or page.get("final_url"))
        for page in client_pages
        if isinstance(page, dict) and (page.get("url") or page.get("final_url"))
    ]
    selected = [
        item for item in candidates[:max(1, min(max_candidates, 3))]
        if isinstance(item, dict) and isinstance(item.get("url"), str)
    ]
    if not selected:
        return {
            "status": "no_candidates",
            "pages_checked": 0,
            "items": [],
            "potential_gaps": [],
            "notice": "No candidate pages were available for content comparison.",
        }

    limits = FetchLimits(timeout_seconds=2.5, max_redirects=1, max_bytes=250_000)

    async def inspect(item: dict[str, Any]) -> dict[str, Any]:
        url = str(item["url"])
        try:
            host = _host(url)
            robots_url = f"https://{host}/robots.txt"
            fetch_kwargs: dict[str, Any] = {
                "limits": limits,
                "allowed_hosts": {host},
            }
            if client is not None:
                fetch_kwargs["client"] = client
            if resolver is not None:
                fetch_kwargs["resolver"] = resolver
            try:
                robots = await fetch_text_document(
                    robots_url,
                    accepted_content_types={"text/plain", "application/octet-stream"},
                    **fetch_kwargs,
                )
                if 200 <= robots.status_code < 300:
                    parts = urlsplit(url)
                    path = parts.path or "/"
                    if parts.query:
                        path += "?" + parts.query
                    decision = evaluate_robots_path(
                        body=robots.body, path=path, user_agent="OutreachMarketingAgentAudit"
                    )
                    if not decision["allowed"]:
                        return {
                            "domain": item.get("domain", host),
                            "url": url,
                            "status": "skipped_robots",
                            "reason": "robots_txt_disallows_page",
                        }
                elif robots.status_code not in {404, 410}:
                    return {
                        "domain": item.get("domain", host),
                        "url": url,
                        "status": "unavailable",
                        "reason": "robots_txt_not_successful",
                    }
            except (ValueError, OSError, httpx.HTTPError):
                return {
                    "domain": item.get("domain", host),
                    "url": url,
                    "status": "unavailable",
                    "reason": "robots_txt_unavailable",
                }

            fetched = await fetch_html(url, **fetch_kwargs)
            if not 200 <= fetched.status_code < 300:
                return {
                    "domain": item.get("domain", host),
                    "url": url,
                    "status": "unavailable",
                    "reason": f"http_{fetched.status_code}",
                }
            parsed = analyze_html(
                page_url=fetched.final_url, html=fetched.body, status_code=fetched.status_code
            )["observations"]
            page = {
                "title": parsed.get("title"),
                "meta_descriptions": parsed.get("meta_descriptions", []),
                "headings": parsed.get("headings", {}),
            }
            competitor_text = _page_text(page)
            query_matches = []
            for query in target_queries:
                score, matched = _coverage(query, competitor_text)
                if score >= 0.34:
                    query_matches.append({
                        "query": query,
                        "coverage": score,
                        "matched_terms": matched,
                    })
            return {
                "domain": item.get("domain", host),
                "url": fetched.final_url,
                "status": "analyzed",
                "title": parsed.get("title"),
                "meta_descriptions": parsed.get("meta_descriptions", []),
                "headings": parsed.get("headings", {}),
                "query_matches": query_matches,
                "evidence_type": "fetched_public_page_metadata_and_headings",
            }
        except (ValueError, OSError, httpx.HTTPError):
            return {
                "domain": item.get("domain", ""),
                "url": url,
                "status": "unavailable",
                "reason": "page_fetch_or_validation_failed",
            }

    semaphore = asyncio.Semaphore(3)

    async def bounded(item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await inspect(item)

    results = await asyncio.gather(*(bounded(item) for item in selected))
    analyzed = [item for item in results if item.get("status") == "analyzed"]
    gaps: list[dict[str, Any]] = []
    for page in analyzed:
        competitor_text = _page_text(page)
        for query in target_queries:
            competitor_score, competitor_terms = _coverage(query, competitor_text)
            own_score, own_terms = _coverage(query, own_text)
            if competitor_score < 0.34 or own_score >= 0.20:
                continue
            gaps.append({
                "query": query,
                "classification": "potential_content_coverage_gap",
                "priority_score": round((competitor_score - own_score) * 100, 1),
                "confidence": "medium" if len(own_urls) >= 3 else "low",
                "client_coverage": own_score,
                "competitor_coverage": competitor_score,
                "competitor_matched_terms": competitor_terms,
                "client_matched_terms": own_terms,
                "competitor_evidence_url": page["url"],
                "client_pages_checked": len(own_urls),
                "client_evidence_urls": own_urls[:8],
                "requires_human_review": True,
            })
    gaps.sort(key=lambda item: (-item["priority_score"], item["query"], item["competitor_evidence_url"]))
    return {
        "status": "completed" if analyzed else "unavailable",
        "pages_checked": len(results),
        "pages_analyzed": len(analyzed),
        "items": results,
        "potential_gaps": gaps[:12],
        "notice": (
            "Potential gaps compare fetched competitor title, meta description and headings "
            "with the bounded set of client pages crawled. They are not proof of site-wide absence, "
            "competitor status, search demand, rankings or traffic impact."
        ),
    }
