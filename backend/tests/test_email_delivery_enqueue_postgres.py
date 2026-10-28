"""PostgreSQL integration tests for approved email enqueue and send-time policy gates.

Runs only against the dedicated disposable OMA_TEST_DATABASE_URL database and applies
the numbered migrations before creating uniquely scoped fixture data.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.services.delivery_store import DeliveryStore


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_email_enqueue_is_approved_workspace_scoped_idempotent_and_suppression_aware():
    asyncio.run(_exercise_email_enqueue_lifecycle())


async def _exercise_email_enqueue_lifecycle() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    workspace_id = "email-enqueue-" + uuid4().hex
    other_workspace_id = "email-enqueue-other-" + uuid4().hex
    actor_id, other_actor_id = uuid4(), uuid4()
    campaign_ids: dict[str, UUID] = {}
    prospect_ids: dict[str, UUID] = {}
    draft_ids: dict[str, UUID] = {}

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
        for actor, suffix in ((actor_id, "a"), (other_actor_id, "b")):
            await connection.execute(
                """INSERT INTO app_users (id,email,password_hash,email_verified_at,status)
                   VALUES ($1,$2,'integration-test-hash',now(),'active')""",
                actor, f"{actor.hex}-{suffix}@example.test",
            )

        async def seed_prospect(key: str, *, workspace: str = workspace_id, actor: UUID = actor_id,
                                email: str | None = None, stage: str = "new") -> UUID:
            prospect_id = uuid4()
            await connection.execute(
                """INSERT INTO crm_prospects
                   (id,workspace_id,name,company,contact_email,website_url,evidence_url,fit_reason,stage,created_by)
                   VALUES ($1,$2,$3,'Integration Co',$4,'https://example.test/',
                           $5,'Verified integration fit',$6,$7)""",
                prospect_id, workspace, "Prospect " + key, email or f"{prospect_id.hex}@example.test",
                f"https://example.test/evidence/{prospect_id.hex}", stage, actor,
            )
            prospect_ids[key] = prospect_id
            return prospect_id

        async def seed_campaign(key: str, *, status: str = "active", workspace: str = workspace_id,
                                actor: UUID = actor_id) -> UUID:
            campaign_id = uuid4()
            await connection.execute(
                """INSERT INTO outreach_campaigns
                   (id,workspace_id,name,client_business,client_offer,target_customer_profile,status,created_by)
                   VALUES ($1,$2,$3,'Integration business','Integration offer','Integration audience',$4,$5)""",
                campaign_id, workspace, "Campaign " + key, status, actor,
            )
            campaign_ids[key] = campaign_id
            return campaign_id

        async def seed_draft(key: str, *, status: str = "approved", campaign_status: str = "active",
                             email: str | None = None, stage: str = "new",
                             workspace: str = workspace_id, actor: UUID = actor_id,
                             other_workspace: bool = False) -> UUID:
            effective_actor = other_actor_id if other_workspace else actor
            effective_workspace = other_workspace_id if other_workspace else workspace
            prospect_id = await seed_prospect(
                key, workspace=effective_workspace, actor=effective_actor, email=email, stage=stage
            )
            campaign_id = await seed_campaign(
                key, status=campaign_status, workspace=effective_workspace, actor=effective_actor
            )
            draft_id = uuid4()
            await connection.execute(
                """INSERT INTO outreach_drafts
                   (id,workspace_id,campaign_id,prospect_id,channel,subject,body,source_evidence_url,
                    status,created_by,reviewed_by,reviewed_at)
                   VALUES ($1,$2,$3,$4,'email',$5,$6,$7,$8,$9,
                           CASE WHEN $8='pending_approval' THEN NULL ELSE $9::uuid END,
                           CASE WHEN $8='pending_approval' THEN NULL ELSE now() END)""",
                draft_id, effective_workspace, campaign_id, prospect_id,
                "Subject " + key, "Approved trusted body " + key,
                f"https://example.test/evidence/{prospect_id.hex}", status, effective_actor,
            )
            draft_ids[key] = draft_id
            return draft_id

        await seed_draft("approved")
        await seed_draft("approved-two")
        await seed_draft("pending", status="pending_approval")
        await seed_draft("rejected", status="rejected")
        await seed_draft("paused", campaign_status="paused")
        await seed_draft("archived", campaign_status="archived")
        await seed_draft("suppressed")
        await connection.execute(
            """INSERT INTO outreach_contact_controls(workspace_id,prospect_id,email_suppressed,updated_by)
               VALUES ($1,$2,TRUE,$3)""",
            workspace_id, prospect_ids["suppressed"], actor_id,
        )
        await seed_draft("do-not-contact", stage="do_not_contact")
        await seed_draft("missing-email", email=None)
        await connection.execute(
            "UPDATE crm_prospects SET contact_email=NULL WHERE id=$1", prospect_ids["missing-email"]
        )
        await seed_draft("foreign", other_workspace=True)
    finally:
        await connection.close()

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    try:
        store = DeliveryStore(pool)

        # Only an approved draft in an active campaign can enter the send queue.
        for key, expected in (
            ("pending", "draft_not_approved"),
            ("rejected", "draft_not_approved"),
            ("paused", "campaign_paused"),
            ("archived", "campaign_archived"),
            ("suppressed", "contact_suppressed"),
            ("do-not-contact", "contact_suppressed"),
            ("missing-email", "prospect_email_required"),
        ):
            with pytest.raises(ValueError, match=expected):
                await store.enqueue(
                    workspace_id=workspace_id, draft_id=draft_ids[key], actor_id=actor_id,
                    idempotency_key="enqueue-" + key + "-001",
                )

        # A draft ID from another tenant is indistinguishable from a missing draft.
        with pytest.raises(LookupError, match="draft_not_found"):
            await store.enqueue(
                workspace_id=workspace_id, draft_id=draft_ids["foreign"], actor_id=actor_id,
                idempotency_key="enqueue-foreign-001",
            )

        first = await store.enqueue(
            workspace_id=workspace_id, draft_id=draft_ids["approved"], actor_id=actor_id,
            idempotency_key="enqueue-approved-001",
        )
        replay = await store.enqueue(
            workspace_id=workspace_id, draft_id=draft_ids["approved"], actor_id=actor_id,
            idempotency_key="enqueue-approved-001",
        )
        assert first["id"] == replay["id"]
        assert first["status"] == "queued"

        # A retry for the same draft with a changed key resolves to the one canonical
        # delivery. Reusing an existing key for a different draft is a hard conflict.
        alternate_key_replay = await store.enqueue(
            workspace_id=workspace_id, draft_id=draft_ids["approved"], actor_id=actor_id,
            idempotency_key="enqueue-other-key-001",
        )
        assert alternate_key_replay["id"] == first["id"]
        with pytest.raises(ValueError, match="idempotency_key_conflict"):
            await store.enqueue(
                workspace_id=workspace_id, draft_id=draft_ids["approved-two"], actor_id=actor_id,
                idempotency_key="enqueue-approved-001",
            )

        # Send-time checks are repeated: approval, campaign state, and suppression can
        # change after queueing but before a worker claims the message.
        for key, mutate_sql, args, expected in (
            ("approval-revoked",
             "UPDATE outreach_drafts SET status='rejected',reviewed_at=now() WHERE id=$1",
             (draft_ids["approved"],), "draft_not_approved"),
        ):
            # Keep this mutation for the final assertion; this also proves no sendable
            # payload is returned after human approval is revoked.
            async with pool.acquire() as conn:
                await conn.execute(mutate_sql, *args)
            with pytest.raises(ValueError, match=expected):
                await store.claim(workspace_id=workspace_id, delivery_id=UUID(first["id"]))

        async with pool.acquire() as conn:
            status = await conn.fetchval(
                "SELECT status FROM outreach_deliveries WHERE id=$1", UUID(first["id"])
            )
        assert status == "queued", "a rejected claim must leave the delivery unclaimed"
    finally:
        await pool.close()
