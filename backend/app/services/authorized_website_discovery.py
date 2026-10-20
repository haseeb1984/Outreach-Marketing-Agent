"""Workspace-authorized website discovery orchestration.

This service is deliberately not an HTTP endpoint. The caller must derive
workspace_id from authenticated server-side identity and inject a persistent
DomainAuthorizationStore. Authorization happens before any target network request.
"""
from __future__ import annotations

from typing import Any

from app.services.website_discovery import discover_and_crawl


async def discover_authorized_website(
    *,
    store: Any,
    workspace_id: str,
    start_url: str,
    max_pages: int = 25,
    max_depth: int = 2,
    limits: Any = None,
    resolver: Any = None,
) -> dict[str, Any]:
    """Authorize the exact target host, then run bounded read-only discovery.

    A caller-supplied workspace ID is not trustworthy by itself; it must come
    from an authenticated principal and server-side workspace membership check.
    This function never accepts a client-provided list of verified domains.
    """
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise PermissionError("An authenticated workspace is required")

    authorization = await store.authorize_url(
        workspace_id=workspace_id,
        url=start_url,
    )
    kwargs: dict[str, Any] = {
        "start_url": authorization["url"],
        "max_pages": max_pages,
        "max_depth": max_depth,
    }
    if limits is not None:
        kwargs["limits"] = limits
    if resolver is not None:
        kwargs["resolver"] = resolver

    report = await discover_and_crawl(**kwargs)
    return {
        "workspace_id": authorization["workspace_id"],
        "authorized_domain": authorization["host"],
        "authorization": "verified_domain_record",
        "discovery": report,
        "limitations": [
            "Authorization uses persisted exact-host verification records.",
            "The caller must authenticate the user and verify workspace membership before calling this service.",
            "This service does not publish website changes or send outreach messages.",
            "Production crawling requires the configured trusted egress proxy to pin validated destination IPs at connection time.",
        ],
    }
}
