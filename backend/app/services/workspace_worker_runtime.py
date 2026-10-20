"""Single-iteration entry point for a durable workspace scan worker.

A process supervisor may call this function repeatedly. It intentionally does not
start a background task from the API process; production callers must inject a
persistent domain store and a connection-time egress policy guard.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from app.services.workspace_scan_worker import process_claimed_website_scan


async def _renew_until_stopped(
    *,
    stop: asyncio.Event,
    lease_lost: asyncio.Event,
    job_queue: Any,
    job_id: str,
    worker_id: str,
    lease_seconds: int,
) -> None:
    """Keep a long scan's lease alive; stop processing if ownership is lost."""
    interval = max(2, min(30, lease_seconds // 3))
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass
        try:
            renewed = await job_queue.extend_lease(
                job_id=job_id,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
        except Exception:
            renewed = False
        if renewed is not True:
            lease_lost.set()
            return


async def run_worker_once(
    *,
    worker_id: str,
    job_queue: Any,
    domain_store: Any,
    egress_guard: Callable[[], Any] | None = None,
    lease_seconds: int = 300,
) -> dict[str, Any]:
    """Claim at most one job, renewing its lease while processing."""
    job = await job_queue.claim(worker_id=worker_id, lease_seconds=lease_seconds)
    if job is None:
        return {"status": "idle"}
    job_id = job.get("id")
    if not isinstance(job_id, str) or not job_id:
        return {"status": "invalid_claim", "reason": "job_id_missing"}

    stop = asyncio.Event()
    lease_lost = asyncio.Event()
    processor = asyncio.create_task(process_claimed_website_scan(
        job=job,
        worker_id=worker_id,
        domain_store=domain_store,
        job_queue=job_queue,
        egress_guard=egress_guard,
    ))
    heartbeat = asyncio.create_task(_renew_until_stopped(
        stop=stop,
        lease_lost=lease_lost,
        job_queue=job_queue,
        job_id=job_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    ))
    lost_waiter = asyncio.create_task(lease_lost.wait())
    try:
        done, _ = await asyncio.wait(
            {processor, lost_waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if lost_waiter in done and lease_lost.is_set() and not processor.done():
            processor.cancel()
            try:
                await processor
            except asyncio.CancelledError:
                pass
            return {"status": "lease_lost", "reason": "job_lease_renewal_failed"}
        return await processor
    finally:
        stop.set()
        heartbeat.cancel()
        if not lost_waiter.done():
            lost_waiter.cancel()
        for task in (heartbeat, lost_waiter):
            try:
                await task
            except asyncio.CancelledError:
                pass


async def run_worker_forever(
    *,
    worker_id: str,
    job_queue: Any,
    domain_store: Any,
    egress_guard: Callable[[], Any] | None = None,
    lease_seconds: int = 300,
    idle_sleep_seconds: float = 2.0,
) -> None:
    """Run a supervised worker loop until its task is cancelled.

    Idle polling is bounded to avoid a hot loop. Cancellation is intentionally
    propagated so process supervisors can stop the worker cleanly.
    """
    if not isinstance(idle_sleep_seconds, (int, float)) or isinstance(idle_sleep_seconds, bool):
        raise ValueError("idle_sleep_seconds must be a number between 0.1 and 60")
    if not 0.1 <= idle_sleep_seconds <= 60:
        raise ValueError("idle_sleep_seconds must be between 0.1 and 60")

    while True:
        result = await run_worker_once(
            worker_id=worker_id,
            job_queue=job_queue,
            domain_store=domain_store,
            egress_guard=egress_guard,
            lease_seconds=lease_seconds,
        )
        if result.get("status") == "idle":
            await asyncio.sleep(idle_sleep_seconds)
