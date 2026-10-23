"""Tests for the bounded orphan WhatsApp quota reconciler; not executed in code-only pass."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from scripts.reconcile_whatsapp_queue_reservations import reconcile_once


class FakeConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.query = ""
        self.args = ()

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetch(self, query, *args):
        self.query, self.args = query, args
        return self.rows


class FakePool:
    def __init__(self, rows=None):
        self.connection = FakeConnection(rows)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_reconciler_releases_only_rows_returned_by_orphan_query():
    pool = FakePool([{"id": uuid4()}, {"id": uuid4()}])
    result = asyncio.run(reconcile_once(pool, older_than_seconds=3600, limit=25))
    assert result == {"orphan_reservations_released": 2}
    query = pool.connection.query
    assert "u.feature='whatsapp_sends'" in query
    assert "u.status='reserved'" in query
    assert "u.idempotency_key LIKE 'whatsapp-send:%'" in query
    assert "NOT EXISTS" in query
    assert "whatsapp_outbound_deliveries q" in query
    assert "FOR UPDATE OF u SKIP LOCKED" in query
    assert pool.connection.args == (3600, 25)


@pytest.mark.parametrize("kwargs", [
    {"older_than_seconds": 3599},
    {"older_than_seconds": 604801},
    {"limit": 0},
    {"limit": 1001},
])
def test_reconciler_rejects_unsafe_bounds(kwargs):
    with pytest.raises(ValueError):
        asyncio.run(reconcile_once(FakePool(), **kwargs))
