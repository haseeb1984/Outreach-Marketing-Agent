"""Persistence-backed entry point for workspace website growth reviews.

This module loads domain authorization from the server-side store rather than accepting
verified-domain records from a caller or HTTP payload.
"""
from __future__ import annotations

from typing import Any

from app.services.website_fetch import FetchLimits, Resolver
from app.services.website_growth_pipeline import discover_and_build_growth_report


async def discover_persisted_workspace_site(
    start_url: str,
    *,
    workspace_id: str,
    domain_store: Any,
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
    """Load active verified domains from persistence before any website network fetch."""
    verified_domains = await domain_store.get_verified_domains(workspace_id=workspace_id)
    return await discover_and_build_growth_report(
        start_url,
        business_type=business_type,
        target_market=target_market,
        target_queries=target_queries,
        workspace_id=workspace_id,
        verified_domains=verified_domains,
        competitor_gaps=competitor_gaps,
        max_pages=max_pages,
        max_depth=max_depth,
        max_sitemaps=max_sitemaps,
        limits=limits,
        resolver=resolver,
    )
