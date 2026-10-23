"""Unit coverage for abandoned outbound-delivery reconciliation."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.services.delivery_store import DeliveryStore


class FakeConnection:
    def __init__(self, result="UPDATE 3"):
        self.result = result
        self.calls = []

    async def execute(self, query, *args):
        self.calls.append((query, args))
        return self.result


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_reconcile_stale_processing_marks_ambiguous_attempts_uncertain():
    connection = FakeConnection("UPDATE 3")
    store = DeliveryStore(FakePool(connection))

    count = asyncio.run(store.reconcile_stale_processing(workspace_id="workspace-a", older_than_seconds=600, limit=20))

    assert count == 3
    query, args = connection.calls[0]
    assert "FOR UPDATE SKIP LOCKED" in query
    assert "status='uncertain'" in query
    assert "worker_lost_outcome_unknown" in query
    assert "status='processing'" in query
    assert "workspace_id=$1" in query
    assert args == ("workspace-a", 600, 20)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"older_than_seconds": 59},
        {"older_than_seconds": 86401},
        {"older_than_seconds": True},
        {"limit": 0},
        {"limit": 501},
        {"limit": False},
    ],
)
def test_reconcile_rejects_unbounded_or_invalid_parameters(kwargs):
    store = DeliveryStore(FakePool(FakeConnection()))
    with pytest.raises(ValueError):
        asyncio.run(store.reconcile_stale_processing(workspace_id="workspace-a", **kwargs))


def test_reconcile_returns_zero_for_unexpected_command_tag():
    store = DeliveryStore(FakePool(FakeConnection("UPDATE")))
    assert asyncio.run(store.reconcile_stale_processing(workspace_id="workspace-a")) == 0
