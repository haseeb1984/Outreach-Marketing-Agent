"""PostgreSQL integration coverage for the account-deletion timestamp contract."""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

from app.db.migrations import apply_migrations


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_deleted_account_requires_timestamp_and_active_account_forbids_it():
    asyncio.run(_exercise_deleted_at_constraint())


async def _exercise_deleted_at_constraint() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)
    connection = await asyncpg.connect(database_url)
    user_id = uuid4()
    email = f"{user_id.hex}@retention-test.example"
    try:
        await connection.execute(
            """INSERT INTO app_users (id,email,password_hash,status)
               VALUES ($1,$2,'integration-test-hash','active')""",
            user_id, email,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                "UPDATE app_users SET status='deleted' WHERE id=$1",
                user_id,
            )
        await connection.execute(
            """UPDATE app_users
               SET status='deleted',deleted_at=now(),email_verified_at=NULL
               WHERE id=$1""",
            user_id,
        )
        deleted_at = await connection.fetchval(
            "SELECT deleted_at FROM app_users WHERE id=$1",
            user_id,
        )
        assert deleted_at is not None

        workspace_id = "deleted-account-trigger-" + user_id.hex
        await connection.execute("INSERT INTO workspaces (id) VALUES ($1)", workspace_id)
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                """INSERT INTO workspace_memberships
                   (workspace_id,user_id,role,status)
                   VALUES ($1,$2,'member','active')""",
                workspace_id, user_id,
            )
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                """INSERT INTO workspace_invitations
                   (workspace_id,invited_email,role,token_sha256,invited_by,expires_at)
                   VALUES ($1,'invitee@example.test','member',$2,$3,now()+interval '1 day')""",
                workspace_id, "a" * 64, user_id,
            )
    finally:
        await connection.execute("DELETE FROM workspaces WHERE id=$1", "deleted-account-trigger-" + user_id.hex)
        await connection.execute("DELETE FROM app_users WHERE id=$1", user_id)
        await connection.close()



@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_workspace_cascade_removes_drafts_deliveries_and_immutable_followup_history():
    asyncio.run(_exercise_workspace_cascade())


async def _exercise_workspace_cascade() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)
    connection = await asyncpg.connect(database_url)
    user_id = uuid4()
    workspace_id = "tenant-cascade-" + user_id.hex
    try:
        await connection.execute(
            """INSERT INTO app_users
               (id,email,password_hash,status,email_verified_at)
               VALUES ($1,$2,'integration-test-hash','active',now())""",
            user_id, f"{user_id.hex}@cascade-test.example",
        )
        await connection.execute("INSERT INTO workspaces (id) VALUES ($1)", workspace_id)
        await connection.execute(
            """INSERT INTO workspace_memberships (workspace_id,user_id,role,status)
               VALUES ($1,$2,'owner','active')""",
            workspace_id, user_id,
        )
        campaign_id = await connection.fetchval(
            """INSERT INTO outreach_campaigns
               (workspace_id,name,client_business,client_offer,target_customer_profile,created_by)
               VALUES ($1,'Test campaign','Test business','Test offer','Test audience',$2)
               RETURNING id""",
            workspace_id, user_id,
        )
        prospect_id = await connection.fetchval(
            """INSERT INTO crm_prospects
               (workspace_id,name,company,website_url,evidence_url,fit_reason,created_by)
               VALUES ($1,'Test prospect','Test company','https://example.test',
                       'https://example.test/evidence','Integration test prospect',$2)
               RETURNING id""",
            workspace_id, user_id,
        )
        draft_id = await connection.fetchval(
            """INSERT INTO outreach_drafts
               (workspace_id,campaign_id,prospect_id,channel,body,source_evidence_url,created_by)
               VALUES ($1,$2,$3,'email','Integration test draft',
                       'https://example.test/evidence',$4)
               RETURNING id""",
            workspace_id, campaign_id, prospect_id, user_id,
        )
        delivery_id = await connection.fetchval(
            """INSERT INTO outreach_deliveries
               (workspace_id,draft_id,channel,idempotency_key,queued_by)
               VALUES ($1,$2,'email',$3,$4) RETURNING id""",
            workspace_id, draft_id, "cascade-" + user_id.hex, user_id,
        )
        sequence_id = await connection.fetchval(
            """INSERT INTO outreach_followup_sequences
               (workspace_id,campaign_id,name,channel,created_by)
               VALUES ($1,$2,'Test sequence','email',$3) RETURNING id""",
            workspace_id, campaign_id, user_id,
        )
        enrollment_id = await connection.fetchval(
            """INSERT INTO outreach_followup_enrollments
               (workspace_id,sequence_id,prospect_id,created_by)
               VALUES ($1,$2,$3,$4) RETURNING id""",
            workspace_id, sequence_id, prospect_id, user_id,
        )
        resolution_id = await connection.fetchval(
            """INSERT INTO outreach_followup_delivery_resolutions
               (workspace_id,enrollment_id,draft_id,delivery_id,channel,outcome,
                reason,evidence_url,resolved_by)
               VALUES ($1,$2,$3,$4,'email','delivered',
                       'Provider delivery confirmed','https://example.test/proof',$5)
               RETURNING id""",
            workspace_id, enrollment_id, draft_id, delivery_id, user_id,
        )

        with pytest.raises(asyncpg.PostgresError, match="immutable"):
            await connection.execute(
                "DELETE FROM outreach_followup_delivery_resolutions WHERE id=$1",
                resolution_id,
            )

        await connection.execute("DELETE FROM workspaces WHERE id=$1", workspace_id)
        remaining = await connection.fetchval(
            """SELECT count(*) FROM outreach_followup_delivery_resolutions
               WHERE id=$1""",
            resolution_id,
        )
        assert remaining == 0
        for table, record_id in (
            ("outreach_deliveries", delivery_id),
            ("outreach_drafts", draft_id),
            ("crm_prospects", prospect_id),
        ):
            remaining = await connection.fetchval(
                f"SELECT count(*) FROM {table} WHERE id=$1",
                record_id,
            )
            assert remaining == 0
    finally:
        await connection.execute("DELETE FROM workspaces WHERE id=$1", workspace_id)
        await connection.execute("DELETE FROM app_users WHERE id=$1", user_id)
        await connection.close()
