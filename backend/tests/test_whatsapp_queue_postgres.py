"""PostgreSQL integration coverage for WhatsApp queue leases and status reconciliation.

Runs only against the dedicated disposable OMA_TEST_DATABASE_URL database. The test
applies the complete numbered migration chain and creates uniquely scoped fixture rows.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.services.whatsapp_outbound_store import WhatsAppOutboundStore
from app.services.whatsapp_status_reconciliation import reconcile_whatsapp_delivery_statuses


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_whatsapp_queue_leases_recovery_and_status_reconciliation():
    asyncio.run(_exercise_whatsapp_queue_lifecycle())


async def _exercise_whatsapp_queue_lifecycle() -> None:
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

        workspace_id = "whatsapp-queue-integration-" + uuid4().hex
        actor_id = uuid4()
        account_id = uuid4()
        await connection.execute("INSERT INTO workspaces (id) VALUES ($1)", workspace_id)
        await connection.execute(
            """INSERT INTO app_users (id,email,password_hash,email_verified_at,status)
               VALUES ($1,$2,'integration-test-hash',now(),'active')""",
            actor_id, f"{actor_id.hex}@example.test",
        )
        await connection.execute(
            """INSERT INTO workspace_whatsapp_accounts
               (id,workspace_id,label,waba_id,phone_number_id,encrypted_access_token,status,created_by)
               VALUES ($1,$2,'Integration account','waba-integration','phone-' || $1::text,
                       NULL,'active',$3)""",
            account_id, workspace_id, actor_id,
        )

        async def seed_delivery(*, suffix: str, provider_message_id: str | None = None) -> UUID:
            prospect_id, campaign_id, draft_id, reservation_id, delivery_id = (
                uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
            )
            await connection.execute(
                """INSERT INTO crm_prospects
                   (id,workspace_id,name,company,website_url,evidence_url,fit_reason,created_by,contact_phone_e164)
                   VALUES ($1,$2,$3,'Integration Co','https://example.test/',
                           'https://example.test/evidence/' || $3,'Integration fixture',$4,'+14155550123')""",
                prospect_id, workspace_id, "Prospect " + suffix, actor_id,
            )
            await connection.execute(
                """INSERT INTO outreach_campaigns
                   (id,workspace_id,name,client_business,client_offer,target_customer_profile,status,created_by)
                   VALUES ($1,$2,$3,'Integration business','Integration offer',
                           'Integration audience','active',$4)""",
                campaign_id, workspace_id, "Campaign " + suffix, actor_id,
            )
            await connection.execute(
                """INSERT INTO outreach_drafts
                   (id,workspace_id,campaign_id,prospect_id,channel,body,source_evidence_url,
                    status,created_by,reviewed_by,reviewed_at)
                   VALUES ($1,$2,$3,$4,'whatsapp','Approved integration message',
                           'https://example.test/evidence/' || $5,'approved',$6,$6,now())""",
                draft_id, workspace_id, campaign_id, prospect_id, "Prospect " + suffix, actor_id,
            )
            await connection.execute(
                """INSERT INTO feature_usage_reservations
                   (id,workspace_id,feature,idempotency_key,billing_period_starts_at,billing_period_ends_at)
                   VALUES ($1,$2,'whatsapp_outreach',$3,now()-interval '1 day',now()+interval '29 days')""",
                reservation_id, workspace_id, "usage-" + suffix + "-" + uuid4().hex,
            )
            await connection.execute(
                """INSERT INTO whatsapp_outbound_deliveries
                   (id,workspace_id,account_id,draft_id,prospect_id,idempotency_key,
                    usage_reservation_id,queued_by,provider_message_id,status)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                delivery_id, workspace_id, account_id, draft_id, prospect_id,
                "queue-" + suffix + "-" + uuid4().hex, reservation_id, actor_id,
                provider_message_id, "uncertain" if provider_message_id else "queued",
            )
            return delivery_id

        queued_ids = [
            await seed_delivery(suffix="lease-a"),
            await seed_delivery(suffix="lease-b"),
        ]
        status_delivery_id = await seed_delivery(
            suffix="status", provider_message_id="wamid.integration." + uuid4().hex
        )
        provider_message_id = await connection.fetchval(
            "SELECT provider_message_id FROM whatsapp_outbound_deliveries WHERE id=$1",
            status_delivery_id,
        )
        # Events arrive out of order; provider timestamps determine the newest state.
        for status, seconds in (("read", 30), ("sent", 10), ("delivered", 20)):
            await connection.execute(
                """INSERT INTO whatsapp_delivery_status_events
                   (workspace_id,account_id,provider_message_id,status,provider_timestamp)
                   VALUES ($1,$2,$3,$4,$5)""",
                workspace_id, account_id, provider_message_id, status,
                datetime.now(timezone.utc) + timedelta(seconds=seconds),
            )
    finally:
        await connection.close()

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    try:
        queue = WhatsAppOutboundStore(pool)
        # Concurrent workers must claim disjoint queue rows using SKIP LOCKED.
        first, second = await asyncio.gather(
            queue.claim_batch(limit=1, lease_seconds=120),
            queue.claim_batch(limit=1, lease_seconds=120),
        )
        assert len(first) == len(second) == 1
        claimed_ids = {first[0]["id"], second[0]["id"]}
        assert claimed_ids == {str(item) for item in queued_ids}
        assert len({first[0]["lease_token"], second[0]["lease_token"]}) == 2

        # An expired lease cannot be completed by its old worker; recovery marks it
        # uncertain instead of putting it back in the sendable queue.
        stale_claim = first[0]
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE whatsapp_outbound_deliveries
                   SET lease_expires_at=now()-interval '1 second' WHERE id=$1""",
                stale_claim["id"],
            )
        assert await queue.finish_claim(
            delivery_id=UUID(stale_claim["id"]),
            lease_token=UUID(stale_claim["lease_token"]),
            outcome="sent",
            provider_message_id="wamid.should-not-be-saved",
        ) is False
        assert await queue.mark_expired_claims_uncertain(limit=10) == 1
        async with pool.acquire() as conn:
            recovered = await conn.fetchrow(
                "SELECT status,error_code,lease_token,lease_expires_at FROM whatsapp_outbound_deliveries WHERE id=$1",
                stale_claim["id"],
            )
            assert recovered["status"] == "uncertain"
            assert recovered["error_code"] == "worker_lease_expired"
            assert recovered["lease_token"] is None
            assert recovered["lease_expires_at"] is None
            # The recovery path must not silently make the row sendable again.
            assert await conn.fetchval(
                "SELECT count(*) FROM whatsapp_outbound_deliveries WHERE id=$1 AND status='queued'",
                stale_claim["id"],
            ) == 0

        # Finish the other still-live lease and prove only the current lease can mutate it.
        live_claim = second[0]
        assert await queue.finish_claim(
            delivery_id=UUID(live_claim["id"]),
            lease_token=__import__("uuid").UUID(live_claim["lease_token"]),
            outcome="sent",
            provider_message_id="wamid.live.integration",
        ) is True
        assert await queue.finish_claim(
            delivery_id=__import__("uuid").UUID(live_claim["id"]),
            lease_token=__import__("uuid").UUID(live_claim["lease_token"]),
            outcome="failed",
            error_code="late_worker",
        ) is False

        # Reconcile the persisted provider statuses: read wins over older sent/delivered,
        # and reconciliation does not send or change unrelated queue rows.
        result = await reconcile_whatsapp_delivery_statuses(
            pool, batch_size=100, workspace_id=workspace_id
        )
        assert result["deliveries_updated"] >= 1
        async with pool.acquire() as conn:
            status = await conn.fetchrow(
                "SELECT status,error_code FROM whatsapp_outbound_deliveries WHERE id=$1",
                status_delivery_id,
            )
            assert status["status"] == "read"
            assert status["error_code"] is None
            assert await conn.fetchval(
                "SELECT status FROM whatsapp_outbound_deliveries WHERE id=$1",
                stale_claim["id"],
            ) == "uncertain"
    finally:
        await pool.close()
