"""Long-running worker for durable, workspace-scoped website growth scans.

Run as a separate process (not inside a serverless request). All jobs are claimed
with PostgreSQL leases, revalidate verified domains, and write results to the
workspace audit history. This worker never sends outreach.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
from uuid import UUID
from typing import Any

import asyncpg

from app.core.config import settings
from app.services.domain_authorization_store import DomainAuthorizationStore
from app.services.subscription_store import SubscriptionStore
from app.services.website_fetch import FetchLimits
from app.services.persisted_website_growth_pipeline import discover_persisted_workspace_site
from app.services.workspace_growth_schedule_runner import WorkspaceGrowthScheduleRunner
from app.services.workspace_job_queue import WorkspaceJobQueue


def _bounded_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("job_payload_invalid")
    start_url = value.get("start_url")
    business_type = value.get("business_type")
    target_market = value.get("target_market")
    requested_by = value.get("requested_by")
    queries = value.get("target_queries", [])
    max_pages = value.get("max_pages", 10)
    max_depth = value.get("max_depth", 2)
    usage_reservation_id = value.get("usage_reservation_id")
    if not all(isinstance(v, str) and v.strip() for v in (start_url, business_type, target_market, requested_by)):
        raise ValueError("job_payload_invalid")
    if not isinstance(queries, list) or len(queries) > 20 or any(not isinstance(q, str) or not q.strip() or len(q) > 200 for q in queries):
        raise ValueError("job_payload_invalid")
    if type(max_pages) is not int or not 1 <= max_pages <= 10:
        raise ValueError("job_payload_invalid")
    if type(max_depth) is not int or not 0 <= max_depth <= 2:
        raise ValueError("job_payload_invalid")
    if usage_reservation_id is not None:
        try:
            usage_reservation_id = str(UUID(str(usage_reservation_id)))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("job_payload_invalid") from None
    return {
        "start_url": start_url.strip(),
        "business_type": business_type.strip()[:160],
        "target_market": target_market.strip()[:160],
        "target_queries": list(dict.fromkeys(q.strip() for q in queries)),
        "max_pages": max_pages,
        "max_depth": max_depth,
        "requested_by": requested_by,
        **({"usage_reservation_id": usage_reservation_id} if usage_reservation_id else {}),
    }


class GrowthJobEntitlementDenied(RuntimeError):
    pass


async def process_one_job(pool: Any, *, worker_id: str) -> bool:
    queue = WorkspaceJobQueue(pool)
    job = await queue.claim(worker_id=worker_id, lease_seconds=300)
    if job is None:
        return False
    try:
        payload = _bounded_payload(job.get("payload"))
        workspace_id = str(job["workspace_id"])
        subscriptions = SubscriptionStore(pool)
        reservation_id = payload.get("usage_reservation_id")
        if reservation_id:
            entitlement = await subscriptions.validate_job_reservation(
                workspace_id=workspace_id,
                reservation_id=reservation_id,
                feature="website_audits",
            )
        else:
            entitlement = await subscriptions.check_feature_enabled(
                workspace_id=workspace_id, feature="website_audits"
            )
        if not entitlement.get("allowed"):
            raise GrowthJobEntitlementDenied()
        domain_store = DomainAuthorizationStore(pool)
        async with asyncio.timeout(240):
            report = await discover_persisted_workspace_site(
                payload["start_url"],
                workspace_id=workspace_id,
                domain_store=domain_store,
                business_type=payload["business_type"],
                target_market=payload["target_market"],
                target_queries=payload["target_queries"],
                max_pages=payload["max_pages"],
                max_depth=payload["max_depth"],
                max_sitemaps=2,
                limits=FetchLimits(timeout_seconds=3.0, max_redirects=2, max_bytes=400_000),
            )
        status = "crawl_skipped" if report.get("crawl_skipped") else "completed"
        async with pool.acquire() as conn:
            saved = await conn.fetchrow(
                """INSERT INTO website_audit_reports
                   (workspace_id,start_url,status,report,requested_by)
                   VALUES ($1,$2,$3,$4::jsonb,$5::uuid)
                   RETURNING id,created_at""",
                workspace_id, report["start_url"], status,
                json.dumps(report, ensure_ascii=False, allow_nan=False),
                payload["requested_by"],
            )
        completed = await queue.complete(
            job_id=job["id"], worker_id=worker_id,
            result={"report_id": str(saved["id"]), "status": status,
                    "created_at": saved["created_at"].isoformat()},
        )
        if not completed:
            # A lease lost after persistence is safe: the unique job/report link is not
            # assumed; a retry may create another report but cannot send messages.
            raise RuntimeError("job_lease_lost_after_persist")
        return True
    except GrowthJobEntitlementDenied:
        await queue.fail(job_id=job["id"], worker_id=worker_id,
                         error_code="growth_scan_entitlement_denied", retry_delay_seconds=0, retry=False)
        return True
    except TimeoutError:
        await queue.fail(job_id=job["id"], worker_id=worker_id,
                         error_code="growth_scan_timeout", retry_delay_seconds=60)
        return True
    except ValueError:
        await queue.fail(job_id=job["id"], worker_id=worker_id,
                         error_code="growth_scan_payload_or_domain_rejected", retry_delay_seconds=0)
        return True
    except Exception:
        # Keep provider, URL, SQL, and credential details out of the durable job record.
        await queue.fail(job_id=job["id"], worker_id=worker_id,
                         error_code="growth_scan_execution_failed", retry_delay_seconds=60)
        return True


async def run_worker(*, poll_seconds: float = 3.0, once: bool = False) -> None:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL must be configured for the worker")
    if not 0.5 <= poll_seconds <= 30:
        raise ValueError("poll_seconds must be between 0.5 and 30")
    pool = await asyncpg.create_pool(
        dsn=settings.database_url, min_size=1, max_size=5, timeout=5, command_timeout=15
    )
    worker_id = f"{socket.gethostname()}:{os.getpid()}"[:200]
    subscriptions = SubscriptionStore(pool)
    schedules = WorkspaceGrowthScheduleRunner(pool, subscriptions)
    try:
        while True:
            try:
                await schedules.enqueue_one_due()
            except Exception:
                # A schedule poll failure must not crash job processing; alerting belongs
                # to the process supervisor/log pipeline and no sensitive details are logged.
                pass
            processed = await process_one_job(pool, worker_id=worker_id)
            if once:
                return
            if not processed:
                await asyncio.sleep(poll_seconds)
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Process durable website growth scan jobs.")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--once", action="store_true", help="enqueue due schedules and process at most one job")
    args = parser.parse_args()
    asyncio.run(run_worker(poll_seconds=args.poll_seconds, once=args.once))


if __name__ == "__main__":
    main()
