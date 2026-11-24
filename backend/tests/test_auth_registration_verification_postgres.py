"""PostgreSQL acceptance for registration, email verification, and first session."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

from app.db.migrations import apply_migrations
from app.services.auth_security import token_digest
from app.services.auth_store import AuthStore


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_registration_verification_and_first_session_lifecycle():
    asyncio.run(_exercise_registration_verification_and_session())


async def _exercise_registration_verification_and_session() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    email = f"registration-{uuid4().hex}@example.test"
    password = "valid-integration-password-123"
    store = AuthStore(pool)
    workspace_id = None
    user_id = None

    try:
        created = await store.register_user(email=email.upper(), password=password)
        assert created is not None
        user_id = created["user_id"]
        workspace_id = created["workspace_id"]
        assert created["email"] == email
        assert await store.authenticate_password(email=email, password=password) is None

        # Duplicate registration is deliberately indistinguishable at the store boundary.
        assert await store.register_user(email=email, password=password) is None

        async with pool.acquire() as connection:
            membership = await connection.fetchrow(
                """SELECT role,status FROM workspace_memberships
                   WHERE workspace_id=$1 AND user_id=$2""",
                workspace_id,
                user_id,
            )
            assert membership["role"] == "owner"
            assert membership["status"] == "active"
            digest = await connection.fetchval(
                """SELECT token_sha256 FROM email_verification_tokens
                   WHERE user_id=$1 AND consumed_at IS NULL""",
                user_id,
            )
            assert digest == token_digest(created["verification_token"])

        # Resend rotates the token and consumes the previous unexpired link.
        replacement = await store.issue_verification_email(email=email)
        assert replacement is not None
        assert await store.verify_email(created["verification_token"]) is False

        # Two concurrent submissions of the replacement token have one winner.
        outcomes = await asyncio.gather(
            store.verify_email(replacement["verification_token"]),
            store.verify_email(replacement["verification_token"]),
        )
        assert sum(outcomes) == 1
        assert await store.verify_email(replacement["verification_token"]) is False

        user = await store.authenticate_password(email=email, password=password)
        assert user is not None
        assert user["user_id"] == user_id

        # Only the verified active account can establish a persistent session.
        session = await store.create_session(user_id=user_id, lifetime_hours=1)
        authenticated = await store.authenticate_session(session["token"])
        assert authenticated is not None
        assert authenticated["user_id"] == user_id

        # A fresh verification token cannot be issued for an already active account.
        assert await store.issue_verification_email(email=email) is None

        async with pool.acquire() as connection:
            user_state = await connection.fetchrow(
                """SELECT status,email_verified_at FROM app_users WHERE id=$1""",
                user_id,
            )
            assert user_state["status"] == "active"
            assert user_state["email_verified_at"] is not None
            token_states = await connection.fetch(
                """SELECT consumed_at FROM email_verification_tokens
                   WHERE user_id=$1""",
                user_id,
            )
            assert token_states and all(row["consumed_at"] is not None for row in token_states)
            audit = await connection.fetchval(
                """SELECT count(*) FROM security_audit_events
                   WHERE workspace_id=$1 AND actor_user_id=$2
                     AND event_type='account.email_verified'
                     AND outcome='success'""",
                workspace_id,
                user_id,
            )
            assert audit == 1
    finally:
        if workspace_id is not None:
            async with pool.acquire() as connection:
                await connection.execute("DELETE FROM workspaces WHERE id=$1", workspace_id)
        if user_id is not None:
            async with pool.acquire() as connection:
                await connection.execute("DELETE FROM app_users WHERE id=$1", user_id)
        await pool.close()
