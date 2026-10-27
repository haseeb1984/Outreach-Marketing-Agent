import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.services.workspace_growth_schedule_runner import WorkspaceGrowthScheduleRunner


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Connection:
    def __init__(self, schedule):
        self.schedule = schedule
        self.queue_insert_args = None
        self.schedule_update_args = None

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        if "FROM workspace_growth_schedules" in query:
            return self.schedule
        if query.lstrip().startswith("INSERT INTO workspace_jobs"):
            self.queue_insert_args = args
            return {
                "id": uuid4(),
                "workspace_id": args[0],
                "job_type": args[1],
                "status": "queued",
                "payload": args[2],
                "attempt_count": 0,
                "max_attempts": args[4],
                "run_after": args[5],
                "created_at": args[5],
            }
        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query, *args):
        if "UPDATE workspace_growth_schedules" in query:
            self.schedule_update_args = args
            return "UPDATE 1"
        raise AssertionError(f"Unexpected execute: {query}")


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


class _Subscriptions:
    def __init__(self, reservation=None):
        self.reservation = reservation or {
            "allowed": True,
            "reason": "reserved",
            "status": "reserved",
            "reservation_id": str(uuid4()),
        }
        self.reserve_args = None
        self.finished = []

    async def reserve_usage(self, **kwargs):
        self.reserve_args = kwargs
        return self.reservation

    async def finish_reservation(self, **kwargs):
        self.finished.append(kwargs)
        return True


def _schedule(schedule_id, slot):
    return {
        "id": schedule_id,
        "workspace_id": "workspace-a",
        "payload": '{"start_url":"https://example.com/","business_type":"SaaS","target_market":"US","target_queries":[],"max_pages":10,"max_depth":2}',
        "interval_hours": 24,
        "next_run_at": slot,
    }


def test_due_schedule_enqueues_quota_metered_idempotent_job_and_advances_next_run():
    schedule_id = uuid4()
    slot = datetime(2026, 10, 28, 0, 0, tzinfo=timezone.utc)
    now = slot + timedelta(hours=53)
    connection = _Connection(_schedule(schedule_id, slot))
    subscriptions = _Subscriptions()
    runner = WorkspaceGrowthScheduleRunner(_Pool(connection), subscriptions)

    result = asyncio.run(runner.enqueue_one_due(now=now))

    assert result["schedule_id"] == str(schedule_id)
    assert result["workspace_id"] == "workspace-a"
    assert result["outcome"] == "enqueued"
    assert connection.queue_insert_args[3] == f"growth-schedule:{schedule_id}:20261028T000000Z"
    assert connection.schedule_update_args[1] == slot + timedelta(hours=72)
    assert connection.schedule_update_args[2] == now
    assert len(connection.schedule_update_args) == 3
    assert subscriptions.reserve_args["feature"] == "website_audits"
    assert subscriptions.reserve_args["idempotency_key"] == f"growth-schedule-usage:{schedule_id}:20261028T000000Z"
    assert subscriptions.finished[0]["outcome"] == "consumed"


def test_schedule_skips_due_slot_when_entitlement_is_denied():
    schedule_id = uuid4()
    slot = datetime(2026, 10, 28, 0, 0, tzinfo=timezone.utc)
    now = slot + timedelta(hours=2)
    connection = _Connection(_schedule(schedule_id, slot))
    subscriptions = _Subscriptions({"allowed": False, "reason": "quota_exhausted"})
    runner = WorkspaceGrowthScheduleRunner(_Pool(connection), subscriptions)

    result = asyncio.run(runner.enqueue_one_due(now=now))

    assert result["outcome"] == "skipped_quota"
    assert result["job_id"] == ""
    assert connection.queue_insert_args is None
    assert connection.schedule_update_args[1] == slot + timedelta(hours=24)
    assert connection.schedule_update_args[3] == "quota_exhausted"
    assert subscriptions.finished == []


def test_scheduler_does_not_enqueue_when_no_schedule_is_due():
    connection = _Connection(None)
    subscriptions = _Subscriptions()
    runner = WorkspaceGrowthScheduleRunner(_Pool(connection), subscriptions)

    result = asyncio.run(runner.enqueue_one_due(now=datetime.now(timezone.utc)))

    assert result is None
    assert connection.queue_insert_args is None
    assert subscriptions.reserve_args is None


def test_scheduler_requires_timezone_aware_clock():
    runner = WorkspaceGrowthScheduleRunner(_Pool(_Connection(None)), _Subscriptions())

    with pytest.raises(ValueError, match="timezone_aware"):
        asyncio.run(runner.enqueue_one_due(now=datetime(2026, 10, 28)))
