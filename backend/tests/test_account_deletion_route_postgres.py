"""Database-backed HTTP acceptance for account deletion and workspace ownership safety."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import httpx
import pytest

from app.api import account_routes
from app.db.migrations import apply_migrations
from app.main import app
from app.services.auth_store import AuthStore
from app.services.auth_security import hash_password


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_account_deletion_requires_ownership_transfer_and_preserves_shared_workspace(monkeypatch):
    asyncio.run(_exercise_account_deletion(monkeypatch))


async def _exercise_account_deletion(monkeypatch) -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)

    user_id = uuid4()
    other_user_id = uuid4()
    email = f"{user_id.hex}@account-delete-integration.example"
    other_email = f"{other_user_id.hex}@account-delete-integration.example"
    shared_workspace = "account-delete-shared-" + user_id.hex
    sole_workspace = "account-delete-sole-" + user_id.hex
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
    previous_pool = getattr(app.state, "db_pool", None)

    auth_store = AuthStore(pool)

    async def authenticated(_request):
        return auth_store, None, {"user_id": str(user_id), "email": email}

    monkeypatch.setattr(account_routes, "_authenticated", authenticated)
    monkeypatch.setattr(account_routes, "_check_csrf", lambda _request, _session: None)
    async def allow_rate_limit(*args, **kwargs):
        return None
    monkeypatch.setattr(account_routes, "_consume", allow_rate_limit)
    app.state.db_pool = pool
    app.state.auth_store = auth_store

    try:
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO app_users
                   (id,email,password_hash,status,email_verified_at)
                   VALUES ($1,$2,$5,'active',now()),
                          ($3,$4,'integration-test-hash','active',now())""",
                user_id, email, other_user_id, other_email, hash_password("integration-test-password").encoded,
            )
            await connection.execute(
                "INSERT INTO workspaces (id,name) VALUES ($1,$2),($3,$4)",
                shared_workspace, "Shared workspace",
                sole_workspace, "Sole workspace",
            )
            await connection.execute(
                """INSERT INTO workspace_memberships
                   (workspace_id,user_id,role,status)
                   VALUES ($1,$2,'owner','active'),
                          ($1,$3,'member','active'),
                          ($4,$2,'owner','active')""",
                shared_workspace, user_id, other_user_id, sole_workspace,
            )
        auth_store = AuthStore(pool)
        live_session = await auth_store.create_session(user_id=user_id, lifetime_hours=1)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            blocked = await client.request("DELETE", "/api/v1/account", json={"password": "integration-test-password"})
            assert blocked.status_code == 409, blocked.text
            assert blocked.json()["detail"] == "transfer_workspace_ownership_before_account_deletion"

            async with pool.acquire() as connection:
                # Simulate the owner transferring the shared workspace to its active member.
                await connection.execute(
                    """UPDATE workspace_memberships SET role='admin',updated_at=now()
                       WHERE workspace_id=$1 AND user_id=$2""",
                    shared_workspace, user_id,
                )
                await connection.execute(
                    """UPDATE workspace_memberships SET role='owner',updated_at=now()
                       WHERE workspace_id=$1 AND user_id=$2""",
                    shared_workspace, other_user_id,
                )

            deleted = await client.delete("/api/v1/account", json={"password": "integration-test-password"})
            assert deleted.status_code == 200, deleted.text
            assert deleted.json()["status"] == "deleted"
            assert deleted.headers["cache-control"] == "no-store, private"
            cookie_headers = deleted.headers.get_list("set-cookie")
            assert any("__Host-oma_session=" in value and ("=;" in value or '=""' in value) for value in cookie_headers)
            assert any("__Host-oma_csrf=" in value and ("=;" in value or '=""' in value) for value in cookie_headers)

        async with pool.acquire() as connection:
            account = await connection.fetchrow(
                "SELECT email,status,deleted_at,email_verified_at FROM app_users WHERE id=$1",
                user_id,
            )
            assert account["status"] == "deleted"
            assert account["deleted_at"] is not None
            assert account["email_verified_at"] is None
            assert account["email"] == f"deleted+{user_id.hex}@accounts.invalid"

            revoked_sessions = await connection.fetchval(
                "SELECT count(*) FROM auth_sessions WHERE user_id=$1 AND revoked_at IS NOT NULL",
                user_id,
            )
            assert revoked_sessions == 1
            assert await auth_store.authenticate_session(live_session["token"]) is None

            shared_owner = await connection.fetchval(
                """SELECT user_id FROM workspace_memberships
                   WHERE workspace_id=$1 AND role='owner' AND status='active'""",
                shared_workspace,
            )
            assert shared_owner == other_user_id

            former_membership = await connection.fetchrow(
                """SELECT role,status FROM workspace_memberships
                   WHERE workspace_id=$1 AND user_id=$2""",
                shared_workspace, user_id,
            )
            assert former_membership["role"] == "admin"
            assert former_membership["status"] == "revoked"

            shared_exists = await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM workspaces WHERE id=$1)",
                shared_workspace,
            )
            sole_exists = await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM workspaces WHERE id=$1)",
                sole_workspace,
            )
            assert shared_exists is True
            assert sole_exists is False

            deletion_events = await connection.fetchval(
                """SELECT count(*) FROM security_audit_events
                   WHERE actor_user_id=$1 AND event_type='account.deleted'
                     AND outcome='success'""",
                user_id,
            )
            assert deletion_events == 1
    finally:
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM workspaces WHERE id=ANY($1::text[])",
                [shared_workspace, sole_workspace],
            )
            await connection.execute(
                "DELETE FROM app_users WHERE id=ANY($1::uuid[])",
                [user_id, other_user_id],
            )
        await pool.close()
        app.state.db_pool = previous_pool
