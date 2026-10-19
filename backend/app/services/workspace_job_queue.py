"""PostgreSQL-backed durable queue for bounded workspace jobs.

Only trusted server code may call these methods with an authenticated workspace ID.
No worker execution or public enqueue endpoint is enabled by this module.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID


ALLOWED_JOB_TYPES = {"website_growth_scan"}
MAX_PAYLOAD_BYTES = 64 * 1024


def validate_job_request(*, job_type: str, payload: dict[str, Any], idempotency_key: str | None) -> str:
    if job_type not in ALLOWED_JOB_TYPES:
        raise ValueError("Unsupported job type")
    if not isinstance(payload, dict):
        raise ValueError("Job payload must be a JSON object")
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Job payload must be valid JSON data") from exc
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("Job payload exceeds the 64 KiB limit")
    if idempotency_key is not None and (
        not isinstance(idempotency_key, str)
        or not idempotency_key.strip()
        or len(idempotency_key) > 200
    ):
        raise ValueError("Idempotency key must contain 1–200 characters")
    return encoded


class WorkspaceJobQueue:
    """Durable queue with idempotency, lease-based claiming, and stale-worker fencing."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def enqueue(
        self,
        *,
        workspace_id: str,
        job_type: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        max_attempts: int = 3,
        run_after: datetime | None = None,
    ) -> dict[str, Any]:
        if not str(workspace_id).strip() or len(str(workspace_id)) > 200:
            raise ValueError("A valid trusted workspace identifier is required")
        if not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        encoded = validate_job_request(
            job_type=job_type, payload=payload, idempotency_key=idempotency_key
        )
        schedule = run_after or datetime.now(timezone.utc)
        if schedule.tzinfo is None or schedule.utcoffset() is None:
            raise ValueError("run_after must be timezone-aware")
        async with self._pool.acquire() as connection:
            if idempotency_key is None:
                row = await connection.fetchrow(
                    """INSERT INTO workspace_jobs
                       (workspace_id, job_type, payload, idempotency_key, max_attempts, run_after)
                       VALUES ($1, $2, $3::jsonb, NULL, $4, $5)
                       RETURNING id, workspace_id, job_type, status, payload,
                                 attempt_count, max_attempts, run_after, created_at""",
                    str(workspace_id), job_type, encoded, max_attempts, schedule,
                )
            else:
                async with connection.transaction():
                    row = await connection.fetchrow(
                        """INSERT INTO workspace_jobs
                           (workspace_id, job_type, payload, idempotency_key, max_attempts, run_after)
                           VALUES ($1, $2, $3::jsonb, $4, $5, $6)
                           ON CONFLICT (workspace_id, job_type, idempotency_key)
                             WHERE idempotency_key IS NOT NULL DO NOTHING
                           RETURNING id, workspace_id, job_type, status, payload,
                                     attempt_count, max_attempts, run_after, created_at""",
                        str(workspace_id), job_type, encoded, idempotency_key, max_attempts, schedule,
                    )
                    if row is None:
                        row = await connection.fetchrow(
                            """SELECT id, workspace_id, job_type, status, payload,
                                      attempt_count, max_attempts, run_after, created_at
                               FROM workspace_jobs
                               WHERE workspace_id=$1 AND job_type=$2 AND idempotency_key=$3""",
                            str(workspace_id), job_type, idempotency_key,
                        )
        result = dict(row)
        if isinstance(result.get("payload"), str):
            result["payload"] = json.loads(result["payload"])
        result["id"] = str(result["id"])
        return result

    async def claim(
        self, *, worker_id: str, lease_seconds: int = 60
    ) -> dict[str, Any] | None:
        if not worker_id or len(worker_id) > 200:
            raise ValueError("A valid worker identifier is required")
        if not 5 <= lease_seconds <= 900:
            raise ValueError("lease_seconds must be between 5 and 900")
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                # Jobs whose final lease expired are marked failed before another claim.
                await connection.execute(
                    """UPDATE workspace_jobs SET status='failed', error_code='lease_expired',
                              locked_by=NULL, locked_at=NULL, lease_expires_at=NULL,
                              finished_at=$1, updated_at=$1
                       WHERE status='running' AND lease_expires_at <= $1
                         AND attempt_count >= max_attempts""",
                    now,
                )
                row = await connection.fetchrow(
                    """SELECT id FROM workspace_jobs
                       WHERE attempt_count < max_attempts AND (
                         (status='queued' AND run_after <= $1)
                         OR (status='running' AND lease_expires_at <= $1)
                       )
                       ORDER BY run_after, created_at
                       FOR UPDATE SKIP LOCKED LIMIT 1""",
                    now,
                )
                if row is None:
                    return None
                job = await connection.fetchrow(
                    """UPDATE workspace_jobs
                       SET status='running', attempt_count=attempt_count+1,
                           locked_by=$2, locked_at=$3,
                           lease_expires_at=$3 + ($4 * interval '1 second'),
                           started_at=COALESCE(started_at, $3), updated_at=$3
                       WHERE id=$1
                       RETURNING id, workspace_id, job_type, status, payload,
                                 attempt_count, max_attempts, lease_expires_at""",
                    row["id"], worker_id, now, lease_seconds,
                )
        result = dict(job)
        if isinstance(result.get("payload"), str):
            result["payload"] = json.loads(result["payload"])
        result["id"] = str(result["id"])
        return result

    async def complete(
        self, *, job_id: str | UUID, worker_id: str, result: dict[str, Any]
    ) -> bool:
        encoded = validate_job_request(
            job_type="website_growth_scan", payload=result, idempotency_key=None
        )
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            status = await connection.execute(
                """UPDATE workspace_jobs
                   SET status='succeeded', result=$3::jsonb, error_code=NULL,
                       locked_by=NULL, locked_at=NULL, lease_expires_at=NULL,
                       finished_at=$4, updated_at=$4
                   WHERE id=$1 AND status='running' AND locked_by=$2
                     AND lease_expires_at > $4""",
                UUID(str(job_id)), worker_id, encoded, now,
            )
        return status.endswith(" 1")

    async def fail(
        self,
        *,
        job_id: str | UUID,
        worker_id: str,
        error_code: str,
        retry_delay_seconds: int = 30,
    ) -> str:
        if not error_code or len(error_code) > 100:
            raise ValueError("error_code must contain 1–100 characters")
        if not 0 <= retry_delay_seconds <= 3600:
            raise ValueError("retry_delay_seconds must be between 0 and 3600")
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """SELECT attempt_count, max_attempts FROM workspace_jobs
                       WHERE id=$1 AND status='running' AND locked_by=$2
                         AND lease_expires_at > $3 FOR UPDATE""",
                    UUID(str(job_id)), worker_id, now,
                )
                if row is None:
                    return "lease_lost"
                terminal = row["attempt_count"] >= row["max_attempts"]
                if terminal:
                    await connection.execute(
                        """UPDATE workspace_jobs SET status='failed', error_code=$3,
                                  locked_by=NULL, locked_at=NULL, lease_expires_at=NULL,
                                  finished_at=$4, updated_at=$4
                           WHERE id=$1 AND locked_by=$2""",
                        UUID(str(job_id)), worker_id, error_code, now,
                    )
                    return "failed"
                await connection.execute(
                    """UPDATE workspace_jobs SET status='queued', error_code=$3,
                              run_after=$4 + ($5 * interval '1 second'),
                              locked_by=NULL, locked_at=NULL, lease_expires_at=NULL,
                              updated_at=$4
                       WHERE id=$1 AND locked_by=$2""",
                    UUID(str(job_id)), worker_id, error_code, now, retry_delay_seconds,
                )
                return "queued_for_retry"
