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

        # A duplicate provider event must not reapply changed data under the same event ID.
        duplicate = make_event(
            first.event_id, NOW + timedelta(minutes=5),
            subscription_status="cancelled",
            entitlements={"email_outreach": {"enabled": False, "monthly_limit": 0}},
        )
        assert await store.apply_verified_event(duplicate) == {"outcome": "duplicate"}

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
    finally:
        await pool.close()
