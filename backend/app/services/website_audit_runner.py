"""Compose bounded retrieval with deterministic HTML inspection."""
from __future__ import annotations

from app.services.website_audit import analyze_html
from app.services.website_fetch import FetchLimits, Resolver, fetch_html


async def audit_website_url(
    url: str,
    *,
    limits: FetchLimits = FetchLimits(),
    resolver: Resolver | None = None,
) -> dict:
    """Audit one public HTML URL without changing the target website.

    This orchestration is intentionally not exposed as an unauthenticated API route.
    Production multi-tenant use must add authenticated workspace ownership, quotas,
    abuse controls, and an egress proxy that pins validated DNS destinations.
    """
    kwargs = {"limits": limits}
    if resolver is not None:
        kwargs["resolver"] = resolver
    fetched = await fetch_html(url, **kwargs)
    report = analyze_html(
        page_url=fetched.final_url,
        html=fetched.body,
        status_code=fetched.status_code,
    )
    report["fetch"] = {
        "requested_url": fetched.requested_url,
        "final_url": fetched.final_url,
        "status_code": fetched.status_code,
        "content_type": fetched.content_type,
        "bytes_received": len(fetched.body.encode("utf-8")),
        "redirected": fetched.requested_url != fetched.final_url,
    }
    report["limitations"].append(
        "Only one page is inspected; robots.txt, sitemap coverage, JavaScript rendering, performance metrics, and search-console data require separate checks."
    )
    return report
