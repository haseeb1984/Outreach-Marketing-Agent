"""Worker for durable, read-only website growth scan jobs.

Run from the backend directory with DATABASE_URL configured:
    python -m app.workers.website_growth_worker
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from app.core.config import settings
from app.services.domain_authorization_store import DomainAuthorizationStore
from app.services.persisted_website_growth_pipeline import discover_persisted_workspace_site
from app.services.workspace_job_queue import WorkspaceJobQueue

logger = logging.getLogger("outreach.worker")
LEASE_SECONDS = 300
HEARTBEAT_SECONDS = 30
POLL_SECONDS = 2
MAX_PAGES = 10
MAX_DEPTH = 2


def validate_scan_payload(payload: Any) -> dict[str, Any]:
    """Normalize the intentionally small, bounded schema accepted by the worker."""
    if not isinstance(payload, dict):
        raise ValueError("payload_must_be_object")
    allowed = {"start_url", "business_type", "target_market", "target_queries", "max_pages", "max_depth"}
    if set(payload) - allowed:
        raise ValueError("payload_has_unsupported_fields")
    start_url = payload.get("start_url")
    if not isinstance(start_url, str) or len(start_url) > 2048:
        raise ValueError("invalid_start_url")
    parsed = urlsplit(start_url)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid_start_url")
    # Do not persist or log arbitrary query strings/fragments that may contain tokens.
    start_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))
    business_type = payload.get("business_type")
    target_market = payload.get("target_market")
    if not isinstance(business_type, str) or not business_type.strip() or len(business_type) > 160:
        raise ValueError("invalid_business_type")
    if not isinstance(target_market, str) or not target_market.strip() or len(target_market) > 160:
        raise ValueError("invalid_target_market")
    queries = payload.get("target_queries", [])
    if not isinstance(queries, list) or len(queries) > 20:
        raise ValueError("invalid_target_queries")
    if any(not isinstance(q, str) or not q.strip() or len(q) > 200 for q in queries):
        raise ValueError("invalid_target_queries")
    max_pages = payload.get("max_pages", MAX_PAGES)
    max_depth = payload.get("max_depth", MAX_DEPTH)
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= MAX_PAGES:
        raise ValueError("max_pages_out_of_range")
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 0 <= max_depth <= MAX_DEPTH:
        raise ValueError("max_depth_out_of_range")
    return {
        "start_url": start_url,
        "business_type": business_type.strip(),
        "target_market": target_market.strip(),
        "target_queries": [q.strip() for q in queries],
        "max_pages": max_pages,
        "max_depth": max_depth,
    }


async def _maintain_lease(queue: WorkspaceJobQueue, job: dict[str, Any], worker_id: str, lost: asyncio.Event) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            extended = await queue.extend_lease(
                job_id=job["id"], worker_id=worker_id, lease_seconds=LEASE_SECONDS
            )
        except Exception:
            logger.warning("worker lease heartbeat failed; job lease is considered lost")
            lost.set()
            return
        if not extended:
            lost.set()
            return


async def process_claimed_job(
    *,
    queue: Any,
    domain_store: Any,
    job: dict[str, Any],
    worker_id: str,
    scan_runner: Callable[..., Awaitable[dict[str, Any]]] = discover_persisted_workspace_site,
) -> str:
    """Execute one claimed job, fencing stale workers and hiding exception details."""
    lost = asyncio.Event()
    heartbeat = asyncio.create_task(_maintain_lease(queue, job, worker_id, lost))
    try:
        try:
            payload = validate_scan_payload(job.get("payload"))
        except ValueError as exc:
            # These codes are authored by validate_scan_payload, never external exception text.
            return await queue.fail(
                job_id=job["id"], worker_id=worker_id, error_code=str(exc)[:100]
            )
        scan_task = asyncio.create_task(scan_runner(
            payload["start_url"],
            workspace_id=str(job["workspace_id"]),
            domain_store=domain_store,
            business_type=payload["business_type"],
            target_market=payload["target_market"],
            target_queries=payload["target_queries"],
            max_pages=payload["max_pages"],
            max_depth=payload["max_depth"],
        ))
        lost_waiter = asyncio.create_task(lost.wait())
        try:
            done, _ = await asyncio.wait(
                {scan_task, lost_waiter}, return_when=asyncio.FIRST_COMPLETED
            )
            if lost_waiter in done and lost.is_set() and not scan_task.done():
                scan_task.cancel()
                try:
                    await scan_task
                except asyncio.CancelledError:
                    pass
                return "lease_lost"
            report = await scan_task
        except ValueError:
            # Avoid persisting potentially sensitive exception details in job metadata.
            return await queue.fail(
                job_id=job["id"], worker_id=worker_id, error_code="website_scan_rejected"
            )
        except asyncio.CancelledError:
            scan_task.cancel()
            raise
        except Exception:
            logger.warning("website growth job failed; recording a generic failure code")
            return await queue.fail(
                job_id=job["id"], worker_id=worker_id, error_code="website_growth_scan_failed"
            )
        finally:
            if not lost_waiter.done():
                lost_waiter.cancel()
            try:
                await lost_waiter
            except asyncio.CancelledError:
                pass
        if lost.is_set():
            return "lease_lost"
        try:
            completed = await queue.complete(job_id=job["id"], worker_id=worker_id, result=report)
        except ValueError:
            return await queue.fail(
                job_id=job["id"], worker_id=worker_id, error_code="website_scan_result_invalid"
            )
        return "succeeded" if completed else "lease_lost"
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass


async def run_worker(*, poll_seconds: float = POLL_SECONDS) -> None:
    """Continuously claim jobs with a bounded pool; Ctrl+C stops cleanly."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the worker")
    if not 0.2 <= poll_seconds <= 30:
        raise ValueError("poll_seconds must be between 0.2 and 30")
    pool = await asyncpg.create_pool(
        dsn=settings.database_url, min_size=1, max_size=3, timeout=5, command_timeout=15
    )
    worker_id = "website-growth-" + secrets.token_hex(12)
    queue = WorkspaceJobQueue(pool)
    domain_store = DomainAuthorizationStore(pool)
    logger.info("website growth worker started")
    error_backoff = poll_seconds
    try:
        while True:
            try:
                job = await queue.claim(worker_id=worker_id, lease_seconds=LEASE_SECONDS)
                if job is None:
                    error_backoff = poll_seconds
                    await asyncio.sleep(poll_seconds)
                    continue
                outcome = await process_claimed_job(
                    queue=queue, domain_store=domain_store, job=job, worker_id=worker_id
                )
                error_backoff = poll_seconds
                logger.info("website growth job finished with outcome=%s", outcome)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Avoid hammering PostgreSQL during outages. This delay is local
                # process state only and is capped so recovery remains responsive.
                logger.error("worker iteration failed; retrying after a bounded delay")
                await asyncio.sleep(error_backoff)
                error_backoff = _next_error_backoff(error_backoff, poll_seconds)
    finally:
        await pool.close()


def _next_error_backoff(current: float, minimum: float) -> float:
    """Double a transient-error delay while respecting polling and hard caps."""
    return min(30.0, max(minimum, current * 2))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
