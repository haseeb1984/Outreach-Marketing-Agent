"""Tests for bounded one-shot delivery reconciliation worker."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from scripts.reconcile_stale_deliveries import reconcile_once


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.fetch_calls = []

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self.rows


class FakePool:
    def __init__(self, rows, execute_results=None):
        self.connection = FakeConnection(rows)
        self.execute_results = list(execute_results or [])
        self.execute_calls = []

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return self.execute_results.pop(0) if self.execute_results else "UPDATE 1"


def test_reconcile_once_processes_only_bounded_workspace_batches():
    pool = FakePool([{"workspace_id": "w1"}, {"workspace_id": "w2"}], ["UPDATE 2", "UPDATE 3"])
    result = asyncio.run(reconcile_once(pool, older_than_seconds=600, per_workspace_limit=20, max_workspaces=5))

    assert result == {
        "workspaces_seen": 2,
        "deliveries_marked_uncertain": 5,
        "workspace_errors": 0,
    }
    query, args = pool.connection.fetch_calls[0]
    assert "SELECT DISTINCT workspace_id" in query
    assert "LIMIT $2" in query
    assert args == (600, 5)
    assert [args for _, args in pool.execute_calls] == [("w1", 600, 20), ("w2", 600, 20)]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"older_than_seconds": 59},
        {"older_than_seconds": 86401},
        {"per_workspace_limit": 0},
        {"per_workspace_limit": 501},
        {"max_workspaces": 0},
        {"max_workspaces": 1001},
    ],
)
def test_reconcile_once_rejects_unbounded_settings(kwargs):
    with pytest.raises(ValueError):
        asyncio.run(reconcile_once(FakePool([]), **kwargs))


def test_reconcile_once_reports_workspace_errors_without_aborting_other_workspaces():
    pool = FakePool([{"workspace_id": "w1"}, {"workspace_id": "w2"}], ["UPDATE 1"])
    # The fake pool can raise for the first update to exercise the worker's fail-safe path.
    original_execute = pool.execute
    calls = 0

    async def execute(query, *args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("sensitive connection detail")
        return await original_execute(query, *args)

    pool.execute = execute
    result = asyncio.run(reconcile_once(pool))
    assert result["workspaces_seen"] == 2
    assert result["deliveries_marked_uncertain"] == 1
    assert result["workspace_errors"] == 1
