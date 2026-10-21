"""PostgreSQL integration coverage for password-reset lifecycle.

Run against a dedicated disposable database with OMA_TEST_DATABASE_URL set.
The test applies the repository migrations and truncates only that test database.
"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from uuid import uuid4
import asyncpg
import pytest
from app.services.auth_security import hash_password, verify_password
from app.services.auth_store import AuthStore
from app.services.auth_rate_limiter import AuthRateLimiter

@pytest.mark.skipif(not os.getenv("OMA_TEST_DATABASE_URL"),reason="requires a dedicated disposable PostgreSQL test database")
def test_password_reset_is_single_use_revokes_sessions_and_updates_password():
    asyncio.run(_exercise_password_reset())

async def _exercise_password_reset() -> None:
    database_url=os.environ["OMA_TEST_DATABASE_URL"]
    connection=await asyncpg.connect(database_url)
    try:
        migrations=Path(__file__).resolve().parents[1]/"migrations"
        for migration_name in (
            "001_workspace_domain_verification.sql","002_workspace_jobs.sql","003_authentication_foundation.sql",
            "004_auth_rate_limits.sql","005_session_csrf_tokens.sql","006_password_reset_tokens.sql",
            "007_crm_prospects.sql","008_campaigns_and_approval_queue.sql","009_contact_controls.sql",
            "010_outbound_delivery_queue.sql","011_conversation_webhook_inbox.sql"):
            await connection.execute((migrations/migration_name).read_text(encoding="utf-8"))
        await connection.execute("""TRUNCATE TABLE outreach_conversation_messages,outreach_deliveries,
          outreach_contact_controls,outreach_draft_events,outreach_drafts,outreach_campaigns,crm_prospects,
          auth_rate_limit_buckets,security_audit_events,password_reset_tokens,email_verification_tokens,
          auth_sessions,workspace_memberships,app_users,workspace_jobs,domain_verification_challenges,
          workspace_domains,workspaces CASCADE""")
        user_id=uuid4(); workspace_id="auth-reset-integration-"+uuid4().hex
        old_password="initial-password-for-test"
        await connection.execute("""INSERT INTO app_users(id,email,password_hash,email_verified_at,status)
          VALUES($1,$2,$3,now(),'active')""",user_id,f"{user_id.hex}@example.test",hash_password(old_password).encoded)
        await connection.execute("INSERT INTO workspaces(id) VALUES($1)",workspace_id)
        await connection.execute("""INSERT INTO workspace_memberships(workspace_id,user_id,role,status)
          VALUES($1,$2,'owner','active')""",workspace_id,user_id)
    finally: await connection.close()
    pool=await asyncpg.create_pool(database_url,min_size=1,max_size=4)
    try:
        store=AuthStore(pool); session=await store.create_session(user_id=user_id,lifetime_hours=1)
        reset=await store.issue_password_reset(email=f"{user_id.hex}@example.test")
        assert reset is not None
        token=reset["reset_token"]; new_password="updated-password-for-integration"
        outcomes=await asyncio.gather(store.reset_password(token=token,new_password=new_password),
          store.reset_password(token=token,new_password="another-valid-test-password"))
        assert sum(outcomes)==1
        assert await store.authenticate_session(session["token"]) is None
        assert await store.reset_password(token=token,new_password=new_password) is False
    finally: await pool.close()
