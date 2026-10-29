"""Lease-safe dispatcher for recurring workspace website-growth schedules."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from app.services.workspace_job_queue import WorkspaceJobQueue


def _valid_schedule_payload(payload: Any) -> bool:
    """Reject malformed persisted scan inputs before spending quota or enqueueing."""
    if not isinstance(payload, dict):
        return False
    allowed = {"start_url", "business_type", "target_market", "target_queries", "max_pages", "max_depth"}
    if set(payload) - allowed:
        return False
    url = payload.get("start_url")
    if not isinstance(url, str) or not url.strip() or len(url) > 2048:
        return False
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password or port not in (None, 443):
        return False
    for key in ("business_type", "target_market"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 160:
            return False
    queries = payload.get("target_queries", [])
    if not isinstance(queries, list) or len(queries) > 20:
        return False
    if any(not isinstance(q, str) or not q.strip() or len(q) > 200 for q in queries):
        return False
    pages = payload.get("max_pages", 10)
    depth = payload.get("max_depth", 2)
    if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= 10:
        return False
    if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= 2:
        return False
    return True


class WorkspaceGrowthScheduleRunner:
    """Enqueue at most one due schedule per call using a stable idempotency slot."""

    def __init__(self, pool: Any, subscriptions: Any) -> None:
        self._pool = pool
        self._queue = WorkspaceJobQueue(pool)
        self._subscriptions = subscriptions

    async def enqueue_one_due(self, *, now: datetime | None = None) -> dict[str, str] | None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        current = current.astimezone(timezone.utc)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                schedule = await conn.fetchrow(
                    """SELECT id, workspace_id, created_by, payload, interval_hours, next_run_at
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
                try:
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    payload = None
                if not _valid_schedule_payload(payload):
                    # A corrupted persisted schedule must not hold quota forever or
                    # monopolize every scheduler poll. Release only an unconsumed
                    # reservation, record the deterministic error, and skip this slot.
                    if reservation.get("status") == "reserved":
                        await self._subscriptions.finish_reservation(
                            workspace_id=str(schedule["workspace_id"]),
                            reservation_id=reservation["reservation_id"],
                            outcome="released",
                        )
                    await conn.execute(
                        """UPDATE workspace_growth_schedules
                           SET next_run_at=$2, last_attempted_at=$3,
                               last_error_code=$4, updated_at=$3
                           WHERE id=$1 AND status='active'""",
                        schedule_id, next_run_at, current, "schedule_payload_invalid",
                    )
                    return {
                        "schedule_id": str(schedule_id),
                        "job_id": "",
                        "workspace_id": str(schedule["workspace_id"]),
                        "outcome": "invalid_payload",
                    }
                payload = {
                    **payload,
                    "requested_by": str(schedule["created_by"]),
                    "usage_reservation_id": str(reservation["reservation_id"]),
                }
                try:
                    job = await self._queue.enqueue(
                        workspace_id=str(schedule["workspace_id"]),
                        job_type="website_growth_scan",
                        payload=payload,
                        idempotency_key=idempotency_key,
                        max_attempts=3,
                        run_after=current,
                    )
                except ValueError as exc:
                    # Deterministic queue rejection must not pin this schedule to
                    # the same due slot forever. An idempotency conflict may refer
                    # to a job already using this reservation, so never release it.
                    conflict = str(exc) == "idempotency_key_conflict"
                    if not conflict and reservation.get("status") == "reserved":
                        await self._subscriptions.finish_reservation(
                            workspace_id=str(schedule["workspace_id"]),
                            reservation_id=reservation["reservation_id"],
                            outcome="released",
                        )
                    error_code = (
                        "schedule_idempotency_conflict" if conflict
                        else "schedule_job_invalid"
                    )
                    await conn.execute(
                        """UPDATE workspace_growth_schedules
                           SET next_run_at=$2, last_attempted_at=$3,
                               last_error_code=$4, updated_at=$3
                           WHERE id=$1 AND status='active'""",
                        schedule_id, next_run_at, current, error_code,
                    )
                    return {
                        "schedule_id": str(schedule_id),
                        "job_id": "",
                        "workspace_id": str(schedule["workspace_id"]),
                        "outcome": "enqueue_rejected",
                    }
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
