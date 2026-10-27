"""Lease-safe dispatcher for recurring workspace website-growth schedules."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.services.workspace_job_queue import WorkspaceJobQueue


class WorkspaceGrowthScheduleRunner:
    """Enqueue at most one due schedule per call using a stable idempotency slot."""

    def __init__(self, pool: Any, subscriptions: Any) -> None:
        self._pool = pool
        self._queue = WorkspaceJobQueue(pool)
        self._subscriptions = subscriptions

    async def enqueue_one_due(self, *, now: datetime | None = None) -> dict[str, str] | None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now_must_be_timezone_aware")
        current = current.astimezone(timezone.utc)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                schedule = await conn.fetchrow(
                    """SELECT id, workspace_id, payload, interval_hours, next_run_at
                       FROM workspace_growth_schedules
                       WHERE status='active' AND next_run_at <= $1
                       ORDER BY next_run_at, created_at
                       FOR UPDATE SKIP LOCKED LIMIT 1""",
                    current,
                )
                if schedule is None:
                    return None

                schedule_id = UUID(str(schedule["id"]))
                slot = schedule["next_run_at"].astimezone(timezone.utc)
                interval_hours = int(schedule["interval_hours"])
                idempotency_key = (
                    f"growth-schedule:{schedule_id}:{slot.strftime('%Y%m%dT%H%M%SZ')}"
                )
                interval_seconds = interval_hours * 3600
                elapsed_intervals = max(
                    0, math.floor((current - slot).total_seconds() / interval_seconds)
                )
                next_run_at = slot + timedelta(seconds=(elapsed_intervals + 1) * interval_seconds)
                usage_key = f"growth-schedule-usage:{schedule_id}:{slot.strftime('%Y%m%dT%H%M%SZ')}"
                reservation = await self._subscriptions.reserve_usage(
                    workspace_id=str(schedule["workspace_id"]),
                    feature="website_audits",
                    idempotency_key=usage_key,
                    now=current,
                )
                if not reservation.get("allowed"):
                    reason = str(reservation.get("reason", "entitlement_denied"))[:100]
                    await conn.execute(
                        """UPDATE workspace_growth_schedules
                           SET next_run_at=$2, last_attempted_at=$3,
                               last_error_code=$4, updated_at=$3
                           WHERE id=$1 AND status='active'""",
                        schedule_id, next_run_at, current, reason,
                    )
                    return {
                        "schedule_id": str(schedule_id),
                        "job_id": "",
                        "workspace_id": str(schedule["workspace_id"]),
                        "outcome": "skipped_quota",
                    }

                payload = schedule["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                if not isinstance(payload, dict):
                    raise ValueError("schedule_payload_invalid")
                job = await self._queue.enqueue(
                    workspace_id=str(schedule["workspace_id"]),
                    job_type="website_growth_scan",
                    payload=payload,
                    idempotency_key=idempotency_key,
                    max_attempts=3,
                    run_after=current,
                )
                if reservation.get("status") == "reserved":
                    finished = await self._subscriptions.finish_reservation(
                        workspace_id=str(schedule["workspace_id"]),
                        reservation_id=reservation["reservation_id"],
                        outcome="consumed",
                    )
                    if not finished:
                        raise RuntimeError("growth_schedule_quota_persistence_failed")
                await conn.execute(
                    """UPDATE workspace_growth_schedules
                       SET next_run_at=$2, last_enqueued_at=$3,
                           last_attempted_at=$3, last_error_code=NULL, updated_at=$3
                       WHERE id=$1 AND status='active'""",
                    schedule_id, next_run_at, current,
                )
                return {
                    "schedule_id": str(schedule_id),
                    "job_id": str(job["id"]),
                    "workspace_id": str(schedule["workspace_id"]),
                    "outcome": "enqueued",
                }
