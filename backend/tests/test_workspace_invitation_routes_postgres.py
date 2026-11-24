"""PostgreSQL-backed HTTP acceptance for workspace invitation lifecycle."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import httpx
import pytest

from app.api import workspace_invitation_routes
from app.db.migrations import apply_migrations
from app.main import app
from app.services.auth_security import token_digest
from app.services.auth_store import AuthStore


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_workspace_invitation_acceptance_expiry_revocation_and_replay(monkeypatch):
    asyncio.run(_exercise_invitation_lifecycle(monkeypatch))


async def _exercise_invitation_lifecycle(monkeypatch) -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)

    owner_id, valid_user_id, wrong_user_id, expired_user_id, revoked_user_id = [
        uuid4() for _ in range(5)
    ]
    workspace_id = "invitation-lifecycle-" + uuid4().hex
    now = datetime.now(timezone.utc)
    tokens = {
        "valid": "valid-invitation-token-" + uuid4().hex * 2,
        "expired": "expired-invitation-token-" + uuid4().hex * 2,
        "revoked": "revoked-invitation-token-" + uuid4().hex * 2,
    }
    users = [
        (owner_id, "owner"),
        (valid_user_id, "valid"),
        (wrong_user_id, "wrong"),
        (expired_user_id, "expired"),
        (revoked_user_id, "revoked"),
    ]
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
    previous_pool = getattr(app.state, "db_pool", None)
    previous_auth_store = getattr(app.state, "auth_store", None)
    actor = {"user_id": str(valid_user_id), "email": "valid@example.test"}

    async def authenticated(_request):
        return None, None, actor

    monkeypatch.setattr(workspace_invitation_routes, "_authenticated", authenticated)
    monkeypatch.setattr(
        workspace_invitation_routes, "_check_csrf", lambda _request, _session: None
    )
    app.state.db_pool = pool
    app.state.auth_store = AuthStore(pool)

    try:
        async with pool.acquire() as connection:
            await connection.executemany(
                """INSERT INTO app_users
                   (id,email,password_hash,status,email_verified_at)
                   VALUES ($1,$2,'integration-test-hash','active',now())""",
                [
                    (user_id, f"{label}@example.test")
                    for user_id, label in users
                ],
            )
            await connection.execute(
                "INSERT INTO workspaces (id,name) VALUES ($1,$2)",
                workspace_id,
                "Invitation lifecycle acceptance",
            )
            await connection.execute(
                """INSERT INTO workspace_memberships (workspace_id,user_id,role,status)
                   VALUES ($1,$2,'owner','active')""",
                workspace_id,
                owner_id,
            )
            await connection.executemany(
                """INSERT INTO workspace_invitations
                   (workspace_id,invited_email,role,token_sha256,status,invited_by,created_at,expires_at)
                   (workspace_id,invited_email,role,token_sha256,status,invited_by,created_at,expires_at,revoked_at)
                   VALUES ($1,$2,'member',$3,$4,$5,$6,$7,CASE WHEN $4='revoked' THEN $6 ELSE NULL END)""",
                [
                    (
                        workspace_id,
                        "valid@example.test",
                        token_digest(tokens["valid"]),
                        "pending",
                        owner_id,
                        now,
                        now + timedelta(days=2),
                    ),
                    (
                        workspace_id,
                        "expired@example.test",
                        token_digest(tokens["expired"]),
                        "pending",
                        owner_id,
                        now - timedelta(days=9),
                        now - timedelta(days=1),
                    ),
                    (
                        workspace_id,
                        "revoked@example.test",
                        token_digest(tokens["revoked"]),
                        "revoked",
                        owner_id,
                        now - timedelta(days=1),
                        now + timedelta(days=2),
                    ),
                ],
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            # A bearer link cannot be accepted by an account with a different email.
            actor.update(user_id=str(wrong_user_id), email="wrong@example.test")
            mismatch = await client.post(
                "/api/v1/workspaces/invitations/accept",
                json={"token": tokens["valid"]},
            )
            assert mismatch.status_code == 403
            assert mismatch.json()["detail"] == "invitation_email_mismatch"

            # Expired tokens are durably marked expired before the 410 response.
            actor.update(user_id=str(expired_user_id), email="expired@example.test")
            expired = await client.post(
                "/api/v1/workspaces/invitations/accept",
                json={"token": tokens["expired"]},
            )
            assert expired.status_code == 410
            assert expired.json()["detail"] == "invitation_expired"

            # A revoked invitation cannot be accepted.
            actor.update(user_id=str(revoked_user_id), email="revoked@example.test")
            revoked = await client.post(
                "/api/v1/workspaces/invitations/accept",
                json={"token": tokens["revoked"]},
            )
            assert revoked.status_code == 400
            assert revoked.json()["detail"] == "invitation_invalid_or_expired"

            # The intended verified account can accept exactly once.
            actor.update(user_id=str(valid_user_id), email="valid@example.test")
            accepted = await client.post(
                "/api/v1/workspaces/invitations/accept",
                json={"token": tokens["valid"]},
            )
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["workspace_id"] == workspace_id
            assert accepted.json()["role"] == "member"

            replay = await client.post(
                "/api/v1/workspaces/invitations/accept",
                json={"token": tokens["valid"]},
            )
            assert replay.status_code == 400
            assert replay.json()["detail"] == "invitation_invalid_or_expired"

            # Workspace owner can revoke a still-pending invitation through HTTP.
            actor.update(user_id=str(owner_id), email="owner@example.test")
            pending_token = "pending-invitation-token-" + uuid4().hex * 2
            async with pool.acquire() as connection:
                pending_id = await connection.fetchval(
                    """INSERT INTO workspace_invitations
                       (workspace_id,invited_email,role,token_sha256,status,invited_by,created_at,expires_at)
                       VALUES ($1,'pending@example.test','viewer',$2,'pending',$3,$4,$5)
                       RETURNING id""",
                    workspace_id,
                    token_digest(pending_token),
                    owner_id,
                    now,
                    now + timedelta(days=2),
                )
            response = await client.delete(
                f"/api/v1/workspaces/invitations/{pending_id}?workspace_id={workspace_id}"
            )
            assert response.status_code == 200, response.text
            assert response.json()["revoked"] is True

            # Verify durable states, membership, and audit trail.
            async with pool.acquire() as connection:
                states = await connection.fetch(
                    """SELECT invited_email,status FROM workspace_invitations
                       WHERE workspace_id=$1 ORDER BY invited_email""",
                    workspace_id,
                )
                state_by_email = {row["invited_email"]: row["status"] for row in states}
                assert state_by_email["valid@example.test"] == "accepted"
                assert state_by_email["expired@example.test"] == "expired"
                assert state_by_email["revoked@example.test"] == "revoked"
                assert state_by_email["pending@example.test"] == "revoked"

                membership = await connection.fetchrow(
                    """SELECT role,status FROM workspace_memberships
                       WHERE workspace_id=$1 AND user_id=$2""",
                    workspace_id,
                    valid_user_id,
                )
                assert membership["role"] == "member"
                assert membership["status"] == "active"

                audit_events = await connection.fetchval(
                    """SELECT count(*) FROM security_audit_events
                       WHERE workspace_id=$1 AND event_type IN (
                         'workspace.invitation.accepted',
                         'workspace.invitation.expired',
                         'workspace.invitation.revoked'
                       )""",
                    workspace_id,
                )
                assert audit_events >= 3
    finally:
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM workspaces WHERE id=$1", workspace_id
            )
            await connection.execute(
                "DELETE FROM app_users WHERE id=ANY($1::uuid[])",
                [user_id for user_id, _label in users],
            )
        await pool.close()
        app.state.db_pool = previous_pool
        app.state.auth_store = previous_auth_store
