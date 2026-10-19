"""Safe robots.txt and sitemap discovery followed by a bounded website crawl.

This service only reads public documents. It never writes to the target site.
If robots.txt retrieval fails unexpectedly, it fails closed and does not crawl.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlsplit

from app.services.robots_sitemap import analyze_robots_txt, analyze_sitemap_xml
from app.services.website_audit import validate_page_url
from app.services.website_crawler import crawl_website
from app.services.website_fetch import FetchLimits, Resolver, fetch_text_document


def _same_host(left: str, right: str) -> bool:
    return (urlsplit(left).hostname or "").lower().rstrip(".") == (
        urlsplit(right).hostname or ""
    ).lower().rstrip(".")


async def discover_and_crawl(
    start_url: str,
    *,
    max_pages: int = 25,
    max_depth: int = 2,
    limits: FetchLimits = FetchLimits(),
    resolver: Resolver | None = None,
    max_sitemaps: int = 3,
) -> dict:
    """Fetch robots and a small number of sitemap documents, then crawl same-host pages."""
    start = validate_page_url(start_url)
    if not 1 <= max_sitemaps <= 10:
        raise ValueError("max_sitemaps must be between 1 and 10")
    host = (urlsplit(start).hostname or "").lower().rstrip(".")
    fetch_kwargs = {"limits": limits, "allowed_hosts": {host}}
    if resolver is not None:
        fetch_kwargs["resolver"] = resolver

    robots_url = urljoin(start, "/robots.txt")
    robots_text: str | None = None
    robots_analysis: dict | None = None
    robots_fetch_error: str | None = None
    sitemap_urls: list[str] = []
    try:
        robots_response = await fetch_text_document(
            robots_url,
            accepted_content_types={"text/plain", "application/octet-stream"},
            **fetch_kwargs,
        )
        if 200 <= robots_response.status_code < 300:
            robots_text = robots_response.body
            robots_analysis = analyze_robots_txt(robots_url=robots_url, body=robots_text)
            sitemap_urls.extend(robots_analysis["sitemap_urls"])
        elif robots_response.status_code not in {404, 410}:
            robots_fetch_error = f"robots.txt returned HTTP {robots_response.status_code}"
    except (ValueError, OSError) as exc:
        robots_fetch_error = str(exc)

    if robots_fetch_error:
        return {
            "start_url": start,
            "crawl_skipped": True,
            "reason": "robots_txt_unavailable_fail_closed",
            "robots": {"url": robots_url, "error": robots_fetch_error},
            "sitemap_documents": [],
            "crawl": None,
            "limitations": [
                "Crawl was skipped because robots.txt could not be retrieved or validated safely.",
                "No target-site content was changed.",
            ],
        }

    if not sitemap_urls:
        sitemap_urls = [urljoin(start, "/sitemap.xml")]

    pending = list(dict.fromkeys(
        url for url in sitemap_urls
        if _same_host(url, start)
    ))
    sitemap_documents: list[dict] = []
    seed_urls: list[str] = []
    seen_sitemaps: set[str] = set()
    while pending and len(sitemap_documents) < max_sitemaps:
        sitemap_url = pending.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            response = await fetch_text_document(
                sitemap_url,
                accepted_content_types={
                    "application/xml", "text/xml", "application/octet-stream", "text/plain"
                },
                **fetch_kwargs,
            )
            if not 200 <= response.status_code < 300:
                sitemap_documents.append({
                    "url": sitemap_url,
                    "status_code": response.status_code,
                    "error": "Sitemap request did not return a successful status",
                })
                continue
            parsed = analyze_sitemap_xml(sitemap_url=sitemap_url, body=response.body, max_entries=5000)
            sitemap_documents.append({
                "url": sitemap_url,
                "status_code": response.status_code,
                "document_type": parsed["document_type"],
                "entry_count": parsed["entry_count"],
            })
            if parsed["document_type"] == "sitemapindex":
                for child_url in parsed["locations"]:
                    if _same_host(child_url, start) and child_url not in seen_sitemaps and child_url not in pending:
                        pending.append(child_url)
            else:
                for location in parsed["locations"]:
                    if _same_host(location, start) and location not in seed_urls:
                        seed_urls.append(location)
        except (ValueError, OSError) as exc:
            sitemap_documents.append({"url": sitemap_url, "error": str(exc)})

    crawl = await crawl_website(
        start,
        max_pages=max_pages,
        max_depth=max_depth,
        limits=limits,
        resolver=resolver,
        robots_txt=robots_text,
        seed_urls=seed_urls,
    )
    return {
        "start_url": start,
        "crawl_skipped": False,
        "robots": robots_analysis or {
            "url": robots_url,
            "status": "not_found",
            "note": "No robots.txt was published; no robots path rules were available.",
        },
        "sitemap_documents": sitemap_documents,
        "sitemap_seed_urls_discovered": len(seed_urls),
        "crawl": crawl,
        "limitations": [
            "Only same-host sitemap documents and page URLs are followed.",
            "Sitemap documents are capped; remaining sitemap-index entries are not fetched.",
            "Sitemap membership does not establish indexability, indexing, traffic, or rankings.",
            "The crawl is source-HTML-only and does not render JavaScript.",
            *crawl["limitations"],
        ],
    }
