"""Unit coverage for fail-closed WhatsApp send eligibility decisions.

These tests exercise policy decisions with a deterministic fake database connection.
They do not call Meta or send messages.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from app.services.whatsapp_send_policy import WhatsAppSendPolicy


class FakeConnection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.queries = []

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


def run_policy(rows, **overrides):
    workspace_id = "workspace-test"
    account_id = overrides.pop("account_id", uuid4())
    prospect_id = uuid4()
    pool = FakePool(rows)
    policy = WhatsAppSendPolicy(pool)
    kwargs = {
        "workspace_id": workspace_id,
        "account_id": account_id,
        "prospect_id": prospect_id,
        "draft_id": uuid4(),
        "now": datetime(2026, 10, 23, 12, tzinfo=timezone.utc),
    }
    kwargs.update(overrides)
    result = asyncio.run(policy.evaluate(**kwargs))
    return result, pool.connection


def test_inactive_or_wrong_workspace_account_fails_closed():
    result, conn = run_policy([None])
    assert result == {"allowed": False, "reason": "whatsapp_account_not_active"}
    assert len(conn.queries) == 1


def test_missing_prospect_fails_closed():
    result, conn = run_policy([{"id": uuid4(), "has_credentials": True}, None])
    assert result == {"allowed": False, "reason": "prospect_not_found"}
    assert len(conn.queries) == 2


def test_documented_opt_in_is_required_before_contact_preferences_are_checked():
    prospect = {
        "id": uuid4(),
        "contact_phone_e164": "+14155550123",
        "stage": "new",
        "whatsapp_opt_in_at": None,
        "whatsapp_opt_in_evidence_url": None,
    }
    result, conn = run_policy([{"id": uuid4(), "has_credentials": True}, prospect])
    assert result == {"allowed": False, "reason": "documented_whatsapp_opt_in_required"}
    assert len(conn.queries) == 2


def test_do_not_contact_stage_blocks_whatsapp_even_with_opt_in():
    account_id = uuid4()
    prospect = {
        "id": uuid4(),
        "contact_phone_e164": "+14155550123",
        "stage": "do_not_contact",
        "whatsapp_opt_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "whatsapp_opt_in_evidence_url": "https://example.test/consent",
        "whatsapp_account_id": account_id,
    }
    result, conn = run_policy([{"id": uuid4(), "has_credentials": True}, prospect])
    assert result == {"allowed": False, "reason": "contact_suppressed"}
    assert len(conn.queries) == 2


def test_account_specific_opt_out_blocks_send():
    account_id = uuid4()
    prospect = {
        "id": uuid4(),
        "contact_phone_e164": "+14155550123",
        "stage": "new",
        "whatsapp_opt_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "whatsapp_opt_in_evidence_url": "https://example.test/consent",
    }
    preference = {
        "opted_out_at": datetime(2026, 10, 20, tzinfo=timezone.utc),
        "opted_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "last_inbound_at": datetime(2026, 10, 23, 11, tzinfo=timezone.utc),
    }
    result, conn = run_policy([{"id": uuid4(), "has_credentials": True}, prospect, preference], account_id=account_id)
    assert result == {"allowed": False, "reason": "whatsapp_contact_opted_out"}
    assert len(conn.queries) == 3


def test_open_customer_service_window_does_not_require_template():
    account_id = uuid4()
    prospect = {
        "id": uuid4(),
        "contact_phone_e164": "+14155550123",
        "stage": "new",
        "whatsapp_opt_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "whatsapp_opt_in_evidence_url": "https://example.test/consent",
    }
    preference = {
        "opted_out_at": None,
        "opted_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "last_inbound_at": datetime(2026, 10, 23, 11, tzinfo=timezone.utc),
    }
    result, conn = run_policy([{"id": uuid4(), "has_credentials": True}, prospect, preference, {"id": uuid4()}], account_id=account_id)
    assert result == {
        "allowed": True,
        "reason": "customer_service_window_open",
        "requires_approved_template": False,
    }
    assert len(conn.queries) == 4


def test_closed_customer_service_window_requires_approved_provider_template():
    account_id = uuid4()
    prospect = {
        "id": uuid4(),
        "contact_phone_e164": "+14155550123",
        "stage": "new",
        "whatsapp_opt_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "whatsapp_opt_in_evidence_url": "https://example.test/consent",
    }
    preference = {
        "opted_out_at": None,
        "opted_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "last_inbound_at": datetime(2026, 10, 21, 11, tzinfo=timezone.utc),
    }
    result, conn = run_policy(
        [{"id": uuid4(), "has_credentials": True}, prospect, preference, {"id": uuid4()}, None],
        account_id=account_id,
        template_name="approved_notice",
        language_code="en",
    )
    # A missing verified provider template must never be treated as permission to send.
    assert result == {"allowed": False, "reason": "approved_provider_template_not_found"}
    assert len(conn.queries) == 5


def test_active_account_without_encrypted_credentials_fails_closed():
    result, conn = run_policy([{"id": uuid4(), "has_credentials": False}])
    assert result == {"allowed": False, "reason": "whatsapp_account_credentials_missing"}
    assert len(conn.queries) == 1


def test_opt_in_for_different_whatsapp_account_fails_closed():
    account_id = uuid4()
    prospect = {
        "id": uuid4(),
        "contact_phone_e164": "+14155550123",
        "stage": "new",
        "whatsapp_opt_in_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
        "whatsapp_opt_in_evidence_url": "https://example.test/consent",
        "whatsapp_account_id": uuid4(),
    }
    result, conn = run_policy([{"id": account_id, "has_credentials": True}, prospect], account_id=account_id)
    assert result == {"allowed": False, "reason": "whatsapp_opt_in_for_account_required"}
    assert len(conn.queries) == 2
