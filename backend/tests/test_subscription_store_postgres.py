"""PostgreSQL integration tests for atomic usage reservation and quota lifecycle."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from app.services.subscription_store import SubscriptionStore


NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
FEATURE = "email_outreach"


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_usage_reservations_enforce_quota_idempotency_and_terminal_states():
    asyncio.run(_exercise_usage_reservation_lifecycle())


async def _exercise_usage_reservation_lifecycle() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    workspace_id = "usage-reservation-" + uuid4().hex
    other_workspace_id = "usage-reservation-other-" + uuid4().hex
    period_start = NOW - timedelta(days=1)
    period_end = NOW + timedelta(days=29)

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

        await connection.execute("INSERT INTO workspaces (id) VALUES ($1),($2)", workspace_id, other_workspace_id)
        entitlements = {"email_outreach": {"enabled": True, "monthly_limit": 2}}
        for workspace in (workspace_id, other_workspace_id):
            await connection.execute(
                """INSERT INTO workspace_subscriptions
                   (workspace_id,provider,provider_customer_id,provider_subscription_id,status,
                    billing_period_starts_at,billing_period_ends_at,entitlements,plan_slug)
                   VALUES ($1,'integration-test',$2,$3,'active',$4,$5,$6::jsonb,'starter')""",
                workspace, "cus-" + workspace, "sub-" + workspace,
                period_start, period_end, json.dumps(entitlements),
            )
    finally:
        await connection.close()

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=8)
    try:
        store = SubscriptionStore(pool)

        # Concurrent independent keys must serialize on the subscription row and
        # never grant more quota units than the configured limit.
        concurrent = await asyncio.gather(*[
            store.reserve_usage(
                workspace_id=workspace_id, feature=FEATURE,
                idempotency_key=f"parallel-reservation-{index:02d}",
                now=NOW,
            )
            for index in range(8)
        ])
        accepted = [item for item in concurrent if item["allowed"]]
        denied = [item for item in concurrent if not item["allowed"]]
        assert len(accepted) == 2
        assert len(denied) == 6
        assert all(item["reason"] == "quota_exhausted" for item in denied)
        assert len({item["reservation_id"] for item in accepted}) == 2

        # A key replay returns the same reservation and does not consume another unit.
        replay_key = "replay-reservation-key"
        replay_first = await store.reserve_usage(
            workspace_id=other_workspace_id, feature=FEATURE,
            idempotency_key=replay_key, now=NOW,
        )
        replay_second = await store.reserve_usage(
            workspace_id=other_workspace_id, feature=FEATURE,
            idempotency_key=replay_key, now=NOW,
        )
        assert replay_first["allowed"] is True
        assert replay_first["reason"] == "reserved"
        assert replay_second["reason"] == "idempotent_replay"
        assert replay_second["reservation_id"] == replay_first["reservation_id"]

        # Idempotency keys cannot be repurposed for another feature, and a released
        # reservation cannot be revived by retrying the same key.
        conflict = await store.reserve_usage(
            workspace_id=other_workspace_id, feature="whatsapp_outreach",
            idempotency_key=replay_key, now=NOW,
        )
        assert conflict == {"allowed": False, "reason": "idempotency_key_feature_conflict"}
        assert await store.finish_reservation(
            workspace_id=other_workspace_id,
            reservation_id=replay_first["reservation_id"], outcome="released",
        ) is True
        assert await store.finish_reservation(
            workspace_id=other_workspace_id,
            reservation_id=replay_first["reservation_id"], outcome="consumed",
        ) is False
        released_replay = await store.reserve_usage(
            workspace_id=other_workspace_id, feature=FEATURE,
            idempotency_key=replay_key, now=NOW,
        )
        assert released_replay == {"allowed": False, "reason": "reservation_released"}

        # Consuming is terminal too; a second finish cannot rewrite billing history.
        active_key = "consumed-reservation-key"
        active = await store.reserve_usage(
            workspace_id=other_workspace_id, feature=FEATURE,
            idempotency_key=active_key, now=NOW,
        )
        assert active["allowed"] is True
        assert await store.finish_reservation(
            workspace_id=other_workspace_id,
            reservation_id=active["reservation_id"], outcome="consumed",
        ) is True
        assert await store.finish_reservation(
            workspace_id=other_workspace_id,
            reservation_id=active["reservation_id"], outcome="released",
        ) is False
        assert await store.validate_job_reservation(
            workspace_id=other_workspace_id, reservation_id=active["reservation_id"],
            feature=FEATURE, now=NOW,
        ) == {"allowed": True, "reason": "entitled", "reservation_status": "consumed"}

        # Workspace scoping: a valid reservation ID from another tenant is not accepted.
        assert await store.validate_job_reservation(
            workspace_id=workspace_id, reservation_id=active["reservation_id"],
            feature=FEATURE, now=NOW,
        )["allowed"] is False
        assert await store.validate_job_reservation(
            workspace_id=other_workspace_id, reservation_id="not-a-uuid",
            feature=FEATURE, now=NOW,
        ) == {"allowed": False, "reason": "reservation_invalid"}

        # Entitlement reporting reflects both reserved and consumed quota.
        decision = await store.get_entitlement(
            workspace_id=workspace_id, feature=FEATURE, now=NOW,
        )
        assert decision.allowed is False
        assert decision.reason == "quota_exhausted"
        async with pool.acquire() as conn:
            assert await conn.fetchval(
                """SELECT count(*) FROM feature_usage_reservations
                   WHERE workspace_id=$1 AND feature=$2
                     AND billing_period_starts_at=$3 AND billing_period_ends_at=$4
                     AND status IN ('reserved','consumed')""",
                workspace_id, FEATURE, period_start, period_end,
            ) == 2
            assert await conn.fetchval(
                "SELECT count(*) FROM feature_usage_reservations WHERE workspace_id=$1 AND idempotency_key=$2",
                other_workspace_id, replay_key,
            ) == 1
    finally:
        await pool.close()
