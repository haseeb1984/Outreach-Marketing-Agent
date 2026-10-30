"""Evidence-led public search discovery for competitor-page candidates.

Search results are discovery hints, not proof that a business is a direct competitor.
This module does not fetch candidate websites or claim content gaps without page evidence.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
from urllib.parse import urlsplit

import httpx


_WORD = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)


def _host(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            return None
        host = parsed.hostname.lower().rstrip(".")
        if host.startswith("www."):
            host = host[4:]
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")):
            return None
        try:
            ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            pass
        else:
            return None
        if "." not in host or host.replace(".", "").isdigit():
            return None
        return host
    except ValueError:
        return None


def _terms(value: str) -> set[str]:
    return {word.lower() for word in _WORD.findall(value)}


def _candidate(item: object, query: str, own_host: str) -> dict | None:
    if not isinstance(item, dict):
        return None
    url = item.get("url")
    title = item.get("title")
    description = item.get("description")
    if not isinstance(url, str) or len(url) > 2048 or not isinstance(title, str) or not title.strip():
        return None
    host = _host(url)
    if host is None or host == own_host or host.endswith("." + own_host):
        return None
    title = title.strip()[:300]
    description = description.strip()[:1200] if isinstance(description, str) else ""
    query_terms = _terms(query)
    matched = sorted(query_terms & _terms(title + " " + description))
    score = round(100 * len(matched) / max(1, len(query_terms)), 1)
    return {
        "domain": host,
        "title": title,
        "url": url,
        "description": description,
        "matched_queries": [query],
        "relevance_score": score,
        "evidence_type": "public_search_result",
        "competitor_status": "candidate_requires_human_review",
        "requires_human_review": True,
    }


async def discover_competitor_candidates(
    *,
    website_url: str,
    target_queries: list[str],
    api_key: str | None,
    client: httpx.AsyncClient | None = None,
    max_candidates: int = 12,
) -> dict:
    """Find distinct public result domains for target queries; never label them confirmed rivals."""
    own_host = _host(website_url)
    if own_host is None:
        raise ValueError("website_url_must_be_public_https")
    queries = list(dict.fromkeys(
        value.strip() for value in target_queries
        if isinstance(value, str) and value.strip()
    ))[:3]
    if not queries:
        raise ValueError("target_queries_required")
    if not isinstance(api_key, str) or not api_key.strip():
        return {
            "status": "unavailable",
            "reason": "search_provider_not_configured",
            "items": [],
            "notice": "Competitor candidates are unavailable because public search is not configured.",
        }

    async def fetch_all(search_client: httpx.AsyncClient) -> list[tuple[str, list]]:
        async def one(query: str) -> tuple[str, list]:
            response = await search_client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query + " competitors alternatives", "count": "8", "safesearch": "moderate"},
                headers={"Accept": "application/json", "X-Subscription-Token": api_key.strip()},
            )
            if response.status_code != 200:
                raise httpx.HTTPStatusError("search_provider_unavailable", request=response.request, response=response)
            data = response.json()
            web = data.get("web") if isinstance(data, dict) else None
            results = web.get("results") if isinstance(web, dict) else None
            if not isinstance(results, list):
                raise ValueError("search_response_invalid")
            return query, results
        return list(await asyncio.gather(*(one(query) for query in queries)))

    try:
        if client is not None:
            batches = await fetch_all(client)
        else:
            timeout = httpx.Timeout(8.0, connect=3.0)
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False, trust_env=False,
            ) as search_client:
                batches = await fetch_all(search_client)
    except (httpx.HTTPError, ValueError, TypeError):
        return {
            "status": "unavailable",
            "reason": "search_provider_unavailable",
            "items": [],
            "notice": "Public search did not return a usable competitor-candidate snapshot.",
        }

    by_host: dict[str, dict] = {}
    for query, results in batches:
        for raw in results:
            candidate = _candidate(raw, query, own_host)
            if candidate is None:
                continue
            previous = by_host.get(candidate["domain"])
            if previous is None:
                by_host[candidate["domain"]] = candidate
            else:
                previous["matched_queries"] = sorted(set(previous["matched_queries"] + [query]))
                if candidate["relevance_score"] > previous["relevance_score"]:
                    candidate["matched_queries"] = previous["matched_queries"]
                    by_host[candidate["domain"]] = candidate

    items = sorted(
        by_host.values(),
        key=lambda item: (-item["relevance_score"], item["domain"], item["url"]),
    )[:max(1, min(max_candidates, 30))]
    return {
        "status": "completed",
        "provider": "brave_search",
        "queries_checked": queries,
        "items": items,
        "count": len(items),
        "notice": "These are public search-result candidates, not confirmed competitors. Review each business and source before using it in strategy.",
    }
