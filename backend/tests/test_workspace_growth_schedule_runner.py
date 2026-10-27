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


@pytest.mark.asyncio
async def test_due_schedule_enqueues_idempotent_job_and_advances_next_run():
    schedule_id = uuid4()
    slot = datetime(2026, 10, 28, 0, 0, tzinfo=timezone.utc)
    now = slot + timedelta(hours=53)
    schedule = {
        "id": schedule_id,
        "workspace_id": "workspace-a",
        "payload": '{"start_url":"https://example.com/","business_type":"SaaS","target_market":"US","target_queries":[],"max_pages":10,"max_depth":2}',
        "interval_hours": 24,
        "next_run_at": slot,
    }
    connection = _Connection(schedule)
    runner = WorkspaceGrowthScheduleRunner(_Pool(connection))

    result = await runner.enqueue_one_due(now=now)

    assert result["schedule_id"] == str(schedule_id)
    assert result["workspace_id"] == "workspace-a"
    assert connection.queue_insert_args[3] == f"growth-schedule:{schedule_id}:20261028T000000Z"
    assert connection.schedule_update_args[1] == slot + timedelta(hours=72)
    assert connection.schedule_update_args[2] == now


@pytest.mark.asyncio
async def test_scheduler_does_not_enqueue_when_no_schedule_is_due():
    connection = _Connection(None)
    runner = WorkspaceGrowthScheduleRunner(_Pool(connection))

    result = await runner.enqueue_one_due(now=datetime.now(timezone.utc))

    assert result is None
    assert connection.queue_insert_args is None


@pytest.mark.asyncio
async def test_scheduler_requires_timezone_aware_clock():
    runner = WorkspaceGrowthScheduleRunner(_Pool(_Connection(None)))

    with pytest.raises(ValueError, match="timezone-aware"):
        await runner.enqueue_one_due(now=datetime(2026, 10, 28))
