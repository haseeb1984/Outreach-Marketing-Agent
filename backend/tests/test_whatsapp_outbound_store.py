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

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        if not self.rows:
            return []
        row = self.rows.pop(0)
        return row if isinstance(row, list) else [row]


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
        "contact_phone_e164": "+14155550123",
        "whatsapp_opt_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "whatsapp_opt_in_evidence_url": "https://example.test/consent",
        "whatsapp_account_id": uuid4(),
    }])
    with pytest.raises(ValueError, match="approved_draft_and_active_campaign_required"):
        asyncio.run(WhatsAppOutboundStore(pool).enqueue(
            workspace_id="workspace-test", account_id=uuid4(), draft_id=uuid4(),
            actor_id=uuid4(), idempotency_key="queue-key-123", usage_reservation_id=uuid4(),
        ))


def test_find_by_idempotency_key_is_workspace_scoped_and_serializes_record():
    queue_id, account_id, draft_id = uuid4(), uuid4(), uuid4()
    queued_at = datetime(2026, 10, 23, tzinfo=timezone.utc)
    pool = FakePool([{
        "id": queue_id, "account_id": account_id, "draft_id": draft_id,
        "status": "queued", "queued_at": queued_at,
        "template_name": "welcome_offer", "language_code": "en_US",
    }])
    result = asyncio.run(WhatsAppOutboundStore(pool).find_by_idempotency_key(
        workspace_id="workspace-test", idempotency_key="queue-key-123",
    ))
    assert result == {
        "id": str(queue_id),
        "account_id": str(account_id),
        "draft_id": str(draft_id),
        "status": "queued",
        "queued_at": queued_at.isoformat(),
        "template_name": "welcome_offer",
        "language_code": "en_US",
        "replayed": True,
    }
    query, args = pool.connection.queries[0]
    assert "WHERE workspace_id=$1 AND idempotency_key=$2" in query
    assert args == ("workspace-test", "queue-key-123")


def test_queue_persists_only_after_database_gate_checks():
    draft_id, prospect_id, account_id, queue_id = uuid4(), uuid4(), uuid4(), uuid4()
    pool = FakePool([
        {
            "id": draft_id, "prospect_id": prospect_id, "status": "approved",
            "channel": "whatsapp", "campaign_status": "active", "stage": "new",
            "archived_at": None, "active_account_id": account_id,
            "contact_phone_e164": "+14155550123",
            "whatsapp_opt_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "whatsapp_opt_in_evidence_url": "https://example.test/consent",
            "whatsapp_account_id": account_id,
        },
        None,
        None,
        {
            "id": queue_id, "status": "queued",
            "queued_at": datetime(2026, 10, 23, tzinfo=timezone.utc),
        },
    ])
    reservation_id = uuid4()
    result = asyncio.run(WhatsAppOutboundStore(pool).enqueue(
        workspace_id="workspace-test", account_id=account_id, draft_id=draft_id,
        actor_id=uuid4(), idempotency_key="queue-key-123", usage_reservation_id=reservation_id,
    ))
    assert result["id"] == str(queue_id)
    assert result["usage_reservation_id"] == str(reservation_id)
    assert result["status"] == "queued"
    assert result["replayed"] is False
    assert len(pool.connection.queries) == 4

def test_queue_rechecks_account_scoped_consent_before_creating_delivery():
    account_id = uuid4()
    pool = FakePool([{
        "id": uuid4(), "prospect_id": uuid4(), "status": "approved",
        "channel": "whatsapp", "campaign_status": "active", "stage": "new",
        "archived_at": None, "active_account_id": account_id,
        "contact_phone_e164": "+14155550123",
        "whatsapp_opt_in_at": None,
        "whatsapp_opt_in_evidence_url": None,
        "whatsapp_account_id": account_id,
    }])
    with pytest.raises(ValueError, match="documented_whatsapp_opt_in_for_account_required"):
        asyncio.run(WhatsAppOutboundStore(pool).enqueue(
            workspace_id="workspace-test", account_id=account_id, draft_id=uuid4(),
            actor_id=uuid4(), idempotency_key="queue-key-456", usage_reservation_id=uuid4(),
        ))
    assert len(pool.connection.queries) == 1


def test_queue_rechecks_opt_out_before_creating_delivery():
    account_id = uuid4()
    pool = FakePool([
        {
            "id": uuid4(), "prospect_id": uuid4(), "status": "approved",
            "channel": "whatsapp", "campaign_status": "active", "stage": "new",
            "archived_at": None, "active_account_id": account_id,
            "contact_phone_e164": "+14155550123",
            "whatsapp_opt_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "whatsapp_opt_in_evidence_url": "https://example.test/consent",
            "whatsapp_account_id": account_id,
        },
        {
            "opted_out_at": datetime(2026, 10, 20, tzinfo=timezone.utc),
            "opted_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        },
    ])
    with pytest.raises(ValueError, match="whatsapp_contact_opted_out"):
        asyncio.run(WhatsAppOutboundStore(pool).enqueue(
            workspace_id="workspace-test", account_id=account_id, draft_id=uuid4(),
            actor_id=uuid4(), idempotency_key="queue-key-789", usage_reservation_id=uuid4(),
        ))
    assert len(pool.connection.queries) == 2



def test_queue_persists_selected_template_metadata_for_future_dispatch():
    draft_id, prospect_id, account_id, queue_id = uuid4(), uuid4(), uuid4(), uuid4()
    pool = FakePool([
        {
            "id": draft_id, "prospect_id": prospect_id, "status": "approved",
            "channel": "whatsapp", "campaign_status": "active", "stage": "new",
            "archived_at": None, "active_account_id": account_id,
            "contact_phone_e164": "+14155550123",
            "whatsapp_opt_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "whatsapp_opt_in_evidence_url": "https://example.test/consent",
            "whatsapp_account_id": account_id,
        },
        None,
        None,
        {
            "id": queue_id, "status": "queued",
            "queued_at": datetime(2026, 10, 23, tzinfo=timezone.utc),
        },
    ])
    result = asyncio.run(WhatsAppOutboundStore(pool).enqueue(
        workspace_id="workspace-test", account_id=account_id, draft_id=draft_id,
        actor_id=uuid4(), idempotency_key="template-key-123",
        usage_reservation_id=uuid4(), template_name="welcome_offer", language_code="en_US",
    ))
    insert_query, insert_args = pool.connection.queries[-1]
    assert "template_name,language_code" in insert_query
    assert insert_args[-2:] == ("welcome_offer", "en_US")
    assert result["template_name"] == "welcome_offer"
    assert result["language_code"] == "en_US"


def test_queue_rejects_incomplete_template_metadata_before_database_access():
    pool = FakePool([])
    with pytest.raises(ValueError, match="whatsapp_template_metadata_pair_required"):
        asyncio.run(WhatsAppOutboundStore(pool).enqueue(
            workspace_id="workspace-test", account_id=uuid4(), draft_id=uuid4(),
            actor_id=uuid4(), idempotency_key="template-key-456",
            usage_reservation_id=uuid4(), template_name="welcome_offer",
        ))
    assert pool.connection.queries == []



def test_claim_batch_uses_atomic_skip_locked_leases_and_serializes_rows():
    delivery_id, account_id, draft_id, prospect_id = uuid4(), uuid4(), uuid4(), uuid4()
    reservation_id, lease_token = uuid4(), uuid4()
    expires = datetime(2026, 10, 28, 12, 2, tzinfo=timezone.utc)
    pool = FakePool([{
        "id": delivery_id, "workspace_id": "workspace-test", "account_id": account_id,
        "draft_id": draft_id, "prospect_id": prospect_id,
        "usage_reservation_id": reservation_id, "template_name": "welcome",
        "language_code": "en_US", "status": "processing", "attempts": 1,
        "lease_token": lease_token, "lease_expires_at": expires,
    }])
    result = asyncio.run(WhatsAppOutboundStore(pool).claim_batch(limit=5, lease_seconds=120))
    assert result[0]["id"] == str(delivery_id)
    assert result[0]["lease_token"] == str(lease_token)
    assert result[0]["lease_expires_at"] == expires.isoformat()
    query, args = pool.connection.queries[0]
    assert "FOR UPDATE SKIP LOCKED" in query
    assert "status='processing'" in query
    assert "lease_expires_at=now()+($2::int * interval '1 second')" in query
    assert args == (5, 120)


def test_claim_batch_rejects_unsafe_limits_before_database_access():
    pool = FakePool([])
    with pytest.raises(ValueError, match="claim_limit_out_of_range"):
        asyncio.run(WhatsAppOutboundStore(pool).claim_batch(limit=0))
    with pytest.raises(ValueError, match="lease_seconds_out_of_range"):
        asyncio.run(WhatsAppOutboundStore(pool).claim_batch(lease_seconds=5))
    assert pool.connection.queries == []


def test_finish_claim_requires_live_lease_and_clears_lease_fields():
    delivery_id, lease_token = uuid4(), uuid4()
    pool = FakePool([{"id": delivery_id}])
    result = asyncio.run(WhatsAppOutboundStore(pool).finish_claim(
        delivery_id=delivery_id, lease_token=lease_token, outcome="sent",
        provider_message_id="wamid.abc",
    ))
    assert result is True
    query, args = pool.connection.queries[0]
    assert "lease_token=NULL, lease_expires_at=NULL" in query
    assert "lease_expires_at > now()" in query
    assert args == (delivery_id, lease_token, "sent", "wamid.abc", None)


def test_finish_claim_rejects_unknown_outcome_before_database_access():
    pool = FakePool([])
    with pytest.raises(ValueError, match="invalid_delivery_outcome"):
        asyncio.run(WhatsAppOutboundStore(pool).finish_claim(
            delivery_id=uuid4(), lease_token=uuid4(), outcome="queued",
        ))
    assert pool.connection.queries == []


def test_expired_claims_become_uncertain_and_are_not_requeued():
    pool = FakePool([[{"id": uuid4()}, {"id": uuid4()}]])
    result = asyncio.run(WhatsAppOutboundStore(pool).mark_expired_claims_uncertain(limit=10))
    assert result == 2
    query, args = pool.connection.queries[0]
    assert "status='processing' AND lease_expires_at <= now()" in query
    assert "status='uncertain'" in query
    assert "worker_lease_expired" in query
    assert "status='queued'" not in query
    assert args == (10,)
