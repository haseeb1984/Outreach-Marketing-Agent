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

from app.services.auth_security import hash_password, token_digest, verify_password
from app.services.auth_http_security import csrf_token_digest
from app.services.auth_store import AuthStore
from app.services.auth_rate_limiter import AuthRateLimiter


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_password_reset_is_single_use_revokes_sessions_and_updates_password():
    asyncio.run(_exercise_password_reset())


async def _exercise_password_reset() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    connection = await asyncpg.connect(database_url)
    try:
        migrations = Path(__file__).resolve().parents[1] / "migrations"
        for migration_name in (
            "001_workspace_domain_verification.sql",
            "002_workspace_jobs.sql",
            "003_authentication_foundation.sql",
            "004_auth_rate_limits.sql",
            "005_session_csrf_tokens.sql",
        ):
            await connection.execute((migrations / migration_name).read_text(encoding="utf-8"))

        # This test must only ever run against the dedicated CI/test database.
        await connection.execute(
            """TRUNCATE TABLE auth_rate_limit_buckets, security_audit_events,
               password_reset_tokens, email_verification_tokens, auth_sessions,
               workspace_memberships, app_users, workspace_jobs,
               domain_verification_challenges, workspace_domains, workspaces
               CASCADE"""
        )
        user_id = uuid4()
        workspace_id = "auth-reset-integration-" + uuid4().hex
        old_password = "initial-password-for-test"
        await connection.execute(
            """INSERT INTO app_users
               (id, email, password_hash, email_verified_at, status)
               VALUES ($1, $2, $3, now(), 'active')""",
            user_id, f"{user_id.hex}@example.test", hash_password(old_password).encoded,
        )
        await connection.execute("INSERT INTO workspaces (id) VALUES ($1)", workspace_id)
        await connection.execute(
            """INSERT INTO workspace_memberships (workspace_id, user_id, role, status)
               VALUES ($1, $2, 'owner', 'active')""",
            workspace_id, user_id,
        )
    finally:
        await connection.close()

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    try:
        store = AuthStore(pool)
        session = await store.create_session(user_id=user_id, lifetime_hours=1)
        assert len(session["csrf_token"]) >= 32
        async with pool.acquire() as conn:
            stored_csrf_digest = await conn.fetchval(
                "SELECT csrf_token_sha256 FROM auth_sessions WHERE token_sha256=$1",
                token_digest(session["token"]),
            )
        assert stored_csrf_digest == csrf_token_digest(session["csrf_token"])
        authenticated = await store.authenticate_session(session["token"])
        assert authenticated is not None
        assert authenticated["csrf_token_sha256"] == stored_csrf_digest

        # Rotation must revoke the old bearer token and bind a fresh CSRF token to the new session.
        old_session_token = session["token"]
        rotated = await store.rotate_session(current_token=old_session_token)
        assert rotated is not None
        assert rotated["token"] != old_session_token
        assert rotated["csrf_token"] != session["csrf_token"]
        assert await store.authenticate_session(old_session_token) is None
        rotated_auth = await store.authenticate_session(rotated["token"])
        assert rotated_auth is not None
        assert rotated_auth["csrf_token_sha256"] == csrf_token_digest(rotated["csrf_token"])
        session = rotated

        reset = await store.issue_password_reset(email=f"{user_id.hex}@example.test")
        assert reset is not None
        token = reset["reset_token"]
        new_password = "updated-password-for-integration"

        # Competing requests for one bearer token must have exactly one winner.
        outcomes = await asyncio.gather(
            store.reset_password(token=token, new_password=new_password),
            store.reset_password(token=token, new_password="another-valid-test-password"),
        )
        assert sum(outcomes) == 1
        assert await store.authenticate_session(session["token"]) is None
        assert await store.reset_password(token=token, new_password=new_password) is False

        conn = await asyncpg.connect(database_url)
        try:
            row = await conn.fetchrow(
                "SELECT password_hash FROM app_users WHERE id=$1", user_id
            )
            assert row is not None
            assert verify_password(new_password if outcomes[0] else "another-valid-test-password", row["password_hash"])
            stored = await conn.fetchval(
                "SELECT token_sha256 FROM password_reset_tokens WHERE user_id=$1", user_id
            )
            assert stored != token
        finally:
            await conn.close()

        # Concurrent requests must not overrun a fixed-window limit.
        limiter = AuthRateLimiter(pool, secret_key="integration-test-key-" + ("x" * 32))
        rate_results = await asyncio.gather(*[
            limiter.consume(
                namespace="login",
                identifier=f"{user_id.hex}@example.test",
                limit=5,
                window_seconds=60,
            )
            for _ in range(12)
        ])
        assert sum(result["allowed"] for result in rate_results) == 5
        assert all(
            result["remaining"] == 0
            for result in rate_results
            if not result["allowed"]
        )
        async with pool.acquire() as conn:
            stored_digests = await conn.fetch(
                "SELECT key_digest FROM auth_rate_limit_buckets"
            )
            assert len(stored_digests) == 1
            assert user_id.hex not in stored_digests[0]["key_digest"]
    finally:
        await pool.close()

@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_workspace_authorization_enforces_membership_role_and_account_state():
    asyncio.run(_exercise_workspace_authorization())


async def _exercise_workspace_authorization() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    connection = await asyncpg.connect(database_url)
    try:
        migrations = Path(__file__).resolve().parents[1] / "migrations"
        for migration_name in (
            "001_workspace_domain_verification.sql",
            "002_workspace_jobs.sql",
            "003_authentication_foundation.sql",
            "004_auth_rate_limits.sql",
            "005_session_csrf_tokens.sql",
        ):
            await connection.execute((migrations / migration_name).read_text(encoding="utf-8"))

        await connection.execute(
            """TRUNCATE TABLE auth_rate_limit_buckets, security_audit_events,
               password_reset_tokens, email_verification_tokens, auth_sessions,
               workspace_memberships, app_users, workspace_jobs,
               domain_verification_challenges, workspace_domains, workspaces
               CASCADE"""
        )
        user_a, user_b = uuid4(), uuid4()
        workspace_a = "workspace-isolation-a-" + uuid4().hex
        workspace_b = "workspace-isolation-b-" + uuid4().hex
        for user_id, status in ((user_a, "active"), (user_b, "active")):
            await connection.execute(
                """INSERT INTO app_users
                   (id, email, password_hash, email_verified_at, status)
                   VALUES ($1, $2, $3, now(), $4)""",
                user_id, f"{user_id.hex}@example.test",
                hash_password("integration-test-password").encoded, status,
            )
        await connection.execute("INSERT INTO workspaces (id) VALUES ($1), ($2)", workspace_a, workspace_b)
        await connection.execute(
            """INSERT INTO workspace_memberships (workspace_id, user_id, role, status)
               VALUES ($1, $2, 'viewer', 'active'), ($3, $4, 'owner', 'active')""",
            workspace_a, user_a, workspace_b, user_b,
        )
    finally:
        await connection.close()

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
    try:
        store = AuthStore(pool)
        # Membership in one workspace must not grant access to another workspace.
        assert await store.authorize_workspace(
            user_id=user_a, workspace_id=workspace_a, minimum_role="viewer"
        ) is True
        assert await store.authorize_workspace(
            user_id=user_a, workspace_id=workspace_b, minimum_role="viewer"
        ) is False
        assert await store.authorize_workspace(
            user_id=user_b, workspace_id=workspace_a, minimum_role="viewer"
        ) is False
        # Role checks must enforce the requested minimum privilege.
        assert await store.authorize_workspace(
            user_id=user_a, workspace_id=workspace_a, minimum_role="admin"
        ) is False
        assert await store.authorize_workspace(
            user_id=user_b, workspace_id=workspace_b, minimum_role="owner"
        ) is True

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE workspace_memberships SET status='suspended' WHERE workspace_id=$1 AND user_id=$2",
                workspace_a, user_a,
            )
        assert await store.authorize_workspace(
            user_id=user_a, workspace_id=workspace_a, minimum_role="viewer"
        ) is False

        async with pool.acquire() as conn:
            await conn.execute("UPDATE app_users SET status='suspended' WHERE id=$1", user_b)
        assert await store.authorize_workspace(
            user_id=user_b, workspace_id=workspace_b, minimum_role="viewer"
        ) is False
    finally:
        await pool.close()

