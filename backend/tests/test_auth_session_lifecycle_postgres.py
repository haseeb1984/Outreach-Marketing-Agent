"""PostgreSQL acceptance for atomic session rotation and account-scoped revocation."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

from app.db.migrations import apply_migrations
from app.services.auth_store import AuthStore


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_session_rotation_revocation_expiry_and_tenant_scope():
    asyncio.run(_exercise_session_lifecycle())


async def _exercise_session_lifecycle() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    store = AuthStore(pool)
    suffix = uuid4().hex
    workspace_ids: list[str] = []
    user_ids: list[str] = []

    async def create_verified_user(email: str) -> str:
        created = await store.register_user(email=email, password="integration-password-123")
        assert created is not None
        user_id = str(created["user_id"])
        workspace_ids.append(str(created["workspace_id"]))
        user_ids.append(user_id)
        assert await store.verify_email(created["verification_token"]) is True
        return user_id

    try:
        owner_id = await create_verified_user(f"session-owner-{suffix}@example.test")
        other_id = await create_verified_user(f"session-other-{suffix}@example.test")

        current = await store.create_session(user_id=owner_id, user_agent="current-browser")
        rotate_target = await store.create_session(user_id=owner_id, user_agent="old-browser")
        revoke_target = await store.create_session(user_id=owner_id, user_agent="revoke-browser")
        expire_target = await store.create_session(user_id=owner_id, user_agent="expire-browser")
        outsider = await store.create_session(user_id=other_id, user_agent="other-account")

        # Concurrent requests using one bearer token must not both rotate it.
        rotations = await asyncio.gather(
            store.rotate_session(current_token=current["token"], user_agent="rotated-a"),
            store.rotate_session(current_token=current["token"], user_agent="rotated-b"),
        )
        winners = [item for item in rotations if item is not None]
        assert len(winners) == 1
        replacement = winners[0]
        assert await store.authenticate_session(current["token"]) is None
        assert await store.authenticate_session(replacement["token"]) is not None

        # A user cannot revoke a session belonging to another account.
        outsider_session_id = await _session_id_for_token(outsider["token"], pool)
        assert await store.revoke_session_by_id(
            user_id=owner_id,
            session_id=outsider_session_id,
        ) is False
        assert await store.authenticate_session(outsider["token"]) is not None

        # Expired sessions are rejected and cannot be listed/revoked as active.
        async with pool.acquire() as connection:
            await connection.execute(
                """UPDATE auth_sessions
                   SET created_at=now()-interval '2 minutes',
                       last_seen_at=now()-interval '2 minutes',
                       expires_at=now()-interval '1 minute'
                   WHERE token_sha256=$1""",
                _digest(expire_target["token"]),
            )
        assert await store.authenticate_session(expire_target["token"]) is None
        expired_session_id = await _session_id_for_token(expire_target["token"], pool)
        assert await store.revoke_session_by_id(
            user_id=owner_id,
            session_id=expired_session_id,
        ) is False

        # Revoke one specific session, leaving the current replacement intact.
        revoke_id = await _session_id_for_token(revoke_target["token"], pool)
        assert await store.revoke_session_by_id(user_id=owner_id, session_id=revoke_id) is True
        assert await store.revoke_session_by_id(user_id=owner_id, session_id=revoke_id) is False
        assert await store.authenticate_session(revoke_target["token"]) is None
        assert await store.authenticate_session(replacement["token"]) is not None

        # Revoke all remaining sessions except the current one.
        replacement_session_id = await _session_id_for_token(replacement["token"], pool)
        count = await store.revoke_other_sessions(
            user_id=owner_id,
            current_session_id=replacement_session_id,
        )
        assert count == 1  # rotate_target remains live; current replacement is preserved.
        assert await store.authenticate_session(rotate_target["token"]) is None
        assert await store.authenticate_session(replacement["token"]) is not None

        listed = await store.list_sessions(
            user_id=owner_id,
            current_session_id=replacement_session_id,
        )
        assert len(listed) == 1
        assert listed[0]["is_current"] is True
        assert "token" not in listed[0]
        assert "token_sha256" not in listed[0]

        async with pool.acquire() as connection:
            event_types = await connection.fetch(
                """SELECT event_type FROM security_audit_events
                   WHERE actor_user_id=$1 AND outcome='success'
                     AND event_type IN ('account.session.revoked',
                                        'account.sessions.revoked_others')""",
                owner_id,
            )
            assert sum(row["event_type"] == "account.session.revoked" for row in event_types) == 1
            assert sum(row["event_type"] == "account.sessions.revoked_others" for row in event_types) == 1
    finally:
        if workspace_ids:
            async with pool.acquire() as connection:
                await connection.execute(
                    "DELETE FROM workspaces WHERE id = ANY($1::text[])",
                    workspace_ids,
                )
        if user_ids:
            async with pool.acquire() as connection:
                await connection.execute(
                    "DELETE FROM app_users WHERE id = ANY($1::uuid[])",
                    user_ids,
                )
        await pool.close()


async def _session_id_for_token(token: str, pool: asyncpg.Pool):
    from app.services.auth_security import token_digest

    async with pool.acquire() as connection:
        value = await connection.fetchval(
            "SELECT id FROM auth_sessions WHERE token_sha256=$1",
            token_digest(token),
        )
    assert value is not None
    return value


def _digest(token: str) -> str:
    from app.services.auth_security import token_digest

    return token_digest(token)
