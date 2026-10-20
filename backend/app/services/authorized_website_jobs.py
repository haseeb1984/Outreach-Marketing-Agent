"""Create durable website-scan jobs only after persistent workspace-domain authorization.

This is an internal service, not an HTTP endpoint. The caller must authenticate the
principal and check workspace membership before passing the workspace identifier.
Public enqueue remains disabled until connection-time SSRF enforcement is deployed.
"""
from __future__ import annotations

from typing import Any


def _bounded_int(value: int, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


async def enqueue_authorized_website_scan(
    *,
    domain_store: Any,
    job_queue: Any,
    workspace_id: str,
    start_url: str,
    max_pages: int = 25,
    max_depth: int = 2,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Authorize a URL against persisted DNS verification before queuing a bounded scan.

    Authorization is repeated by the worker immediately before network access; this
    enqueue-time check is defense in depth, not a substitute for worker-time checks.
    """
    if not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200:
        raise PermissionError("An authenticated workspace is required")
    max_pages = _bounded_int(max_pages, name="max_pages", minimum=1, maximum=100)
    max_depth = _bounded_int(max_depth, name="max_depth", minimum=0, maximum=5)

    # Store implementation validates URL syntax and exact verified hostname.
    authorization = await domain_store.authorize_url(
        workspace_id=workspace_id,
        url=start_url,
    )
    authorized_workspace = authorization.get("workspace_id")
    if str(authorized_workspace) != workspace_id:
        # Never enqueue using a cross-workspace or malformed authorization result.
        raise PermissionError("Website authorization workspace mismatch")
    authorized_url = authorization.get("url")
    host = authorization.get("host")
    if not isinstance(authorized_url, str) or not authorized_url or not isinstance(host, str) or not host:
        raise PermissionError("Website authorization is incomplete")

    return await job_queue.enqueue(
        workspace_id=workspace_id,
        job_type="website_growth_scan",
        payload={
            "start_url": authorized_url,
            "authorized_domain": host,
            "max_pages": max_pages,
            "max_depth": max_depth,
            "authorization": "verified_domain_record",
        },
        idempotency_key=idempotency_key,
    )
