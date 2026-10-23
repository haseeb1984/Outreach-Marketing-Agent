"""Unit tests for tenant-scoped WhatsApp outbound queue storage; no provider sends."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services.whatsapp_outbound_store import WhatsAppOutboundStore


class FakeConnection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.queries = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        if not self.rows:
            raise AssertionError("unexpected database query")
        return self.rows.pop(0)


class FakePool:
    def __init__(self, rows):
        self.connection = FakeConnection(rows)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_queue_requires_approved_whatsapp_draft_and_active_campaign():
    pool = FakePool([{
        "id": uuid4(), "prospect_id": uuid4(), "status": "pending_approval",
        "channel": "whatsapp", "campaign_status": "active", "stage": "new",
        "archived_at": None, "active_account_id": uuid4(),
    }])
    with pytest.raises(ValueError, match="approved_draft_and_active_campaign_required"):
        asyncio.run(WhatsAppOutboundStore(pool).enqueue(
            workspace_id="workspace-test", account_id=uuid4(), draft_id=uuid4(),
            actor_id=uuid4(), idempotency_key="queue-key-123", usage_reservation_id=uuid4(),
        ))


def test_queue_persists_only_after_database_gate_checks():
    draft_id, prospect_id, account_id, queue_id = uuid4(), uuid4(), uuid4(), uuid4()
    pool = FakePool([
        {
            "id": draft_id, "prospect_id": prospect_id, "status": "approved",
            "channel": "whatsapp", "campaign_status": "active", "stage": "new",
            "archived_at": None, "active_account_id": account_id,
        },
        None,
        {
            "id": queue_id, "status": "queued",
            "queued_at": datetime(2026, 10, 23, tzinfo=timezone.utc),
        },
    ])
    result = asyncio.run(WhatsAppOutboundStore(pool).enqueue(
        workspace_id="workspace-test", account_id=account_id, draft_id=draft_id,
        actor_id=uuid4(), idempotency_key="queue-key-123", usage_reservation_id=uuid4(),
    ))
    assert result["id"] == str(queue_id)
    assert result["status"] == "queued"
    assert result["replayed"] is False
    assert len(pool.connection.queries) == 3
