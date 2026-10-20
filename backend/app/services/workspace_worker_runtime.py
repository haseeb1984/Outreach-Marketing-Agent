"""Single-iteration entry point for a durable workspace scan worker.

A process supervisor may call this function repeatedly. It intentionally does not
start a background task from the API process; production callers must inject a
persistent domain store and a connection-time egress policy guard.
"""
from __future__ import annotations

from typing import Any, Callable

from app.services.workspace_scan_worker import process_claimed_website_scan


async def run_worker_once(
    *,
    worker_id: str,
    job_queue: Any,
    domain_store: Any,
    egress_guard: Callable[[], Any] | None = None,
    lease_seconds: int = 300,
) -> dict[str, Any]:
    """Claim at most one job and process it; return idle without side effects."""
    job = await job_queue.claim(worker_id=worker_id, lease_seconds=lease_seconds)
    if job is None:
        return {"status": "idle"}
    return await process_claimed_website_scan(
        job=job,
        worker_id=worker_id,
        domain_store=domain_store,
        job_queue=job_queue,
        egress_guard=egress_guard,
    )
