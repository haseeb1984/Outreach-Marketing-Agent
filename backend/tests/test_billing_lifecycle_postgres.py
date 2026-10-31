"""PostgreSQL integration tests for verified billing lifecycle event ordering."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from app.services.billing_lifecycle_store import BillingLifecycleStore, VerifiedBillingEvent


NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_billing_events_are_idempotent_ordered_and_subscription_scoped():
    asyncio.run(_exercise_billing_lifecycle())


async def _exercise_billing_lifecycle() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        migrations = Path(__file__).resolve().parents[1] / "migrations"
        migration_files = sorted(migrations.glob("[0-9][0-9][0-9]_*.sql"))
        assert migration_files, "repository migration directory must not be empty"
        for migration_path in migration_files:
            await connection.execute(migration_path.read_text(encoding="utf-8"))
        workspace_id = "billing-lifecycle-" + uuid4().hex
        await connection.execute("INSERT INTO workspaces (id) VALUES ($1)", workspace_id)
    finally:
        await connection.close()

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
    try:
        store = BillingLifecycleStore(pool)

        def make_event(event_id: str, occurred_at: datetime, **overrides) -> VerifiedBillingEvent:
            values = {
                "provider": "test-provider",
                "event_id": event_id,
                "workspace_id": workspace_id,
                "provider_customer_id": "cus_integration",
                "provider_subscription_id": "sub_integration",
                "plan_slug": "starter",
                "event_created_at": occurred_at,
                "subscription_status": "active",
                "period_starts_at": NOW - timedelta(days=1),
                "period_ends_at": NOW + timedelta(days=29),
                "entitlements": {"email_outreach": {"enabled": True, "monthly_limit": 100}},
            }
            values.update(overrides)
            return VerifiedBillingEvent(**values)

        first = make_event("evt_first_" + uuid4().hex, NOW)
        assert await store.apply_verified_event(first) == {"outcome": "applied"}

        # An exact retry is idempotent, but mutating the snapshot under the
        # same provider event ID must be rejected by the payload fingerprint.
        assert await store.apply_verified_event(first) == {"outcome": "duplicate"}
        mutated_duplicate = make_event(
            first.event_id, NOW,
            subscription_status="cancelled",
            entitlements={"email_outreach": {"enabled": False, "monthly_limit": 0}},
        )
        with pytest.raises(ValueError, match="billing_event_payload_conflict"):
            await store.apply_verified_event(mutated_duplicate)

        # Reusing the same provider event ID with a different timestamp is an identity conflict.
        timestamp_collision = make_event(first.event_id, NOW + timedelta(minutes=5))
        with pytest.raises(ValueError, match="billing_event_identity_conflict"):
            await store.apply_verified_event(timestamp_collision)

        # Equal timestamps are deliberately first-committer-wins: a later
        # distinct event at the same provider timestamp cannot replace the snapshot.
        tied = make_event(
            "evt_tied_" + uuid4().hex, NOW,
            subscription_status="cancelled",
            entitlements={"email_outreach": {"enabled": False, "monthly_limit": 0}},
        )
        assert await store.apply_verified_event(tied) == {"outcome": "stale"}
        async with pool.acquire() as conn:
            assert await conn.fetchval(
                "SELECT status FROM workspace_subscriptions WHERE workspace_id=$1",
                workspace_id,
            ) == "active"

        # Older snapshots are retained in the ledger as stale but cannot regress state.
        stale = make_event(
            "evt_stale_" + uuid4().hex, NOW - timedelta(minutes=1),
            subscription_status="past_due",
            entitlements={"email_outreach": {"enabled": False, "monthly_limit": 0}},
        )
        assert await store.apply_verified_event(stale) == {"outcome": "stale"}

        async with pool.acquire() as conn:
            snapshot = await conn.fetchrow(
                """SELECT status,plan_slug,entitlements,provider_event_created_at
                   FROM workspace_subscriptions WHERE workspace_id=$1""",
                workspace_id,
            )
            assert snapshot["status"] == "active"
            assert snapshot["plan_slug"] == "starter"
            entitlements = snapshot["entitlements"]
            if isinstance(entitlements, str):
                import json
                entitlements = json.loads(entitlements)
            assert entitlements["email_outreach"]["monthly_limit"] == 100
            assert snapshot["provider_event_created_at"] == NOW
            outcomes = await conn.fetch(
                """SELECT provider_event_id,outcome FROM billing_provider_events
                   WHERE workspace_id=$1 ORDER BY received_at,provider_event_id""",
                workspace_id,
            )
            assert {row["outcome"] for row in outcomes} == {"applied", "stale"}

        # A different provider subscription cannot take over an existing workspace.
        conflict = make_event(
            "evt_conflict_" + uuid4().hex,
            NOW + timedelta(minutes=10),
            provider_subscription_id="sub_other",
        )
        with pytest.raises(ValueError, match="billing_subscription_identity_conflict"):
            await store.apply_verified_event(conflict)
        async with pool.acquire() as conn:
            assert await conn.fetchval(
                """SELECT count(*) FROM billing_provider_events
                   WHERE provider=$1 AND provider_event_id=$2""",
                conflict.provider, conflict.event_id,
            ) == 0

        # A subscription cannot silently migrate to a different provider customer.
        customer_conflict = make_event(
            "evt_customer_conflict_" + uuid4().hex,
            NOW + timedelta(minutes=11),
            provider_customer_id="cus_unrelated",
        )
        with pytest.raises(ValueError, match="billing_subscription_identity_conflict"):
            await store.apply_verified_event(customer_conflict)
        async with pool.acquire() as conn:
            assert await conn.fetchval(
                """SELECT provider_customer_id FROM workspace_subscriptions WHERE workspace_id=$1""",
                workspace_id,
            ) == "cus_integration"

        # Missing customer IDs in later snapshots must not erase an established link.
        no_customer = make_event(
            "evt_no_customer_" + uuid4().hex,
            NOW + timedelta(minutes=12),
            provider_customer_id=None,
        )
        assert await store.apply_verified_event(no_customer) == {"outcome": "applied"}
        async with pool.acquire() as conn:
            assert await conn.fetchval(
                """SELECT provider_customer_id FROM workspace_subscriptions WHERE workspace_id=$1""",
                workspace_id,
            ) == "cus_integration"

        # Two first-time subscriptions racing for the same workspace must never be
        # silently reported as stale. Exactly one identity wins; the other transaction
        # rolls back its event-ledger row and reports an explicit identity conflict.
        race_workspace = "billing-lifecycle-race-" + uuid4().hex
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO workspaces (id) VALUES ($1)", race_workspace)
        race_a = make_event(
            "evt_race_a_" + uuid4().hex, NOW,
            workspace_id=race_workspace, provider_subscription_id="sub_race_a",
        )
        race_b = make_event(
            "evt_race_b_" + uuid4().hex, NOW,
            workspace_id=race_workspace, provider_subscription_id="sub_race_b",
        )
        results = await asyncio.gather(
            store.apply_verified_event(race_a),
            store.apply_verified_event(race_b),
            return_exceptions=True,
        )
        successes = [result for result in results if isinstance(result, dict)]
        errors = [result for result in results if isinstance(result, ValueError)]
        assert successes == [{"outcome": "applied"}]
        assert len(errors) == 1
        assert str(errors[0]) == "billing_subscription_identity_conflict"
        async with pool.acquire() as conn:
            race_snapshot = await conn.fetchrow(
                "SELECT provider_subscription_id FROM workspace_subscriptions WHERE workspace_id=$1",
                race_workspace,
            )
            assert race_snapshot["provider_subscription_id"] in {"sub_race_a", "sub_race_b"}
            assert await conn.fetchval(
                "SELECT count(*) FROM billing_provider_events WHERE workspace_id=$1",
                race_workspace,
            ) == 1

        # Paddle transaction history: exact event replay is idempotent, payload
        # mutation under the same event ID is rejected, and later snapshots win.
        transaction_id = "txn_integration_" + uuid4().hex
        transaction_event_id = "evt_tx_" + uuid4().hex
        transaction_args = {
            "event_id": transaction_event_id,
            "event_created_at": NOW,
            "transaction_id": transaction_id,
            "workspace_id": workspace_id,
            "subscription_id": "sub_integration",
            "invoice_number": "INV-INTEGRATION",
            "status": "completed",
            "currency_code": "USD",
            "total_minor": "1200",
        }
        assert await store.record_verified_transaction(**transaction_args) == {"outcome": "applied"}
        assert await store.record_verified_transaction(**transaction_args) == {"outcome": "duplicate"}
        with pytest.raises(ValueError, match="billing_transaction_event_payload_conflict"):
            await store.record_verified_transaction(
                **{**transaction_args, "status": "payment_failed"}
            )
        with pytest.raises(ValueError, match="billing_transaction_event_identity_conflict"):
            await store.record_verified_transaction(
                **{**transaction_args, "event_created_at": NOW + timedelta(seconds=1)}
            )

        # A later event for the same transaction advances its status.
        later_transaction_event = {
            **transaction_args,
            "event_id": "evt_tx_later_" + uuid4().hex,
            "event_created_at": NOW + timedelta(minutes=1),
            "status": "payment_failed",
        }
        assert await store.record_verified_transaction(**later_transaction_event) == {"outcome": "applied"}
        # Paddle emits transaction.past_due after a failed renewal attempt.
        past_due_transaction_event = {
            **transaction_args,
            "event_id": "evt_tx_past_due_" + uuid4().hex,
            "event_created_at": NOW + timedelta(minutes=2),
            "status": "past_due",
        }
        assert await store.record_verified_transaction(**past_due_transaction_event) == {"outcome": "applied"}
        # Older/equal events cannot regress the current transaction state.
        tied_transaction_event = {
            **transaction_args,
            "event_id": "evt_tx_tied_" + uuid4().hex,
            "status": "completed",
        }
        assert await store.record_verified_transaction(**tied_transaction_event) == {"outcome": "stale"}
        async with pool.acquire() as conn:
            transaction_snapshot = await conn.fetchrow(
                "SELECT status,total_minor,currency_code FROM billing_transactions WHERE provider='paddle' AND transaction_id=$1",
                transaction_id,
            )
            assert transaction_snapshot["status"] == "past_due"
            assert str(transaction_snapshot["total_minor"]) == "1200"
            assert transaction_snapshot["currency_code"] == "USD"

        # A transaction's settled currency and total are immutable across later events.
        for value_overrides in (
            {"currency_code": "EUR"},
            {"total_minor": "1300"},
        ):
            conflicting_value_event_id = "evt_tx_value_conflict_" + uuid4().hex
            with pytest.raises(ValueError, match="billing_transaction_value_conflict"):
                await store.record_verified_transaction(
                    **{
                        **transaction_args,
                        **value_overrides,
                        "event_id": conflicting_value_event_id,
                        "event_created_at": NOW + timedelta(minutes=2),
                    }
                )
            async with pool.acquire() as conn:
                assert await conn.fetchval(
                    "SELECT count(*) FROM billing_transaction_events WHERE provider='paddle' AND provider_event_id=$1",
                    conflicting_value_event_id,
                ) == 0

        # Concurrent first events for one transaction cannot race two different totals
        # into the same billing record. The losing event must roll back its ledger row.
        concurrent_transaction_id = "txn_concurrent_" + uuid4().hex
        concurrent_events = [
            {
                **transaction_args,
                "transaction_id": concurrent_transaction_id,
                "event_id": "evt_tx_concurrent_a_" + uuid4().hex,
                "event_created_at": NOW + timedelta(minutes=3),
                "total_minor": "2100",
            },
            {
                **transaction_args,
                "transaction_id": concurrent_transaction_id,
                "event_id": "evt_tx_concurrent_b_" + uuid4().hex,
                "event_created_at": NOW + timedelta(minutes=3),
                "total_minor": "2200",
            },
        ]
        concurrent_results = await asyncio.gather(
            *(store.record_verified_transaction(**event) for event in concurrent_events),
            return_exceptions=True,
        )
        assert sum(result == {"outcome": "applied"} for result in concurrent_results) == 1
        value_conflicts = [
            result for result in concurrent_results
            if isinstance(result, ValueError) and str(result) == "billing_transaction_value_conflict"
        ]
        assert len(value_conflicts) == 1
        async with pool.acquire() as conn:
            concurrent_snapshot = await conn.fetchrow(
                "SELECT total_minor FROM billing_transactions WHERE provider='paddle' AND transaction_id=$1",
                concurrent_transaction_id,
            )
            assert str(concurrent_snapshot["total_minor"]) in {"2100", "2200"}
            assert await conn.fetchval(
                """SELECT count(*) FROM billing_transaction_events
                   WHERE provider='paddle' AND transaction_id=$1""",
                concurrent_transaction_id,
            ) == 1

        # A transaction ID cannot be rebound to a different workspace.
        other_workspace = "billing-transaction-other-" + uuid4().hex
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO workspaces (id) VALUES ($1)", other_workspace)
        with pytest.raises(ValueError, match="billing_transaction_workspace_conflict"):
            await store.record_verified_transaction(
                **{
                    **transaction_args,
                    "event_id": "evt_tx_workspace_conflict_" + uuid4().hex,
                    "event_created_at": NOW + timedelta(minutes=2),
                    "workspace_id": other_workspace,
                }
            )
    finally:
        await pool.close()
