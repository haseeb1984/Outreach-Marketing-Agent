"""PostgreSQL-backed HTTP acceptance for tenant membership role enforcement."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import httpx
import pytest

from app.api import workspace_member_routes
from app.db.migrations import apply_migrations
from app.main import app
from app.services.auth_store import AuthStore


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_workspace_member_role_changes_enforce_owner_admin_and_tenant_boundaries(monkeypatch):
    asyncio.run(_exercise_member_role_authorization(monkeypatch))


async def _exercise_member_role_authorization(monkeypatch) -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)

    owner_id, admin_id, member_id, second_admin_id, outsider_id = [uuid4() for _ in range(5)]
    workspace_id = "member-role-http-" + uuid4().hex
    other_workspace_id = "member-role-outsider-" + uuid4().hex
    users = [
        (owner_id, "owner"),
        (admin_id, "admin"),
        (member_id, "member"),
        (second_admin_id, "second-admin"),
        (outsider_id, "outsider"),
    ]
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
    previous_pool = getattr(app.state, "db_pool", None)
    previous_auth_store = getattr(app.state, "auth_store", None)
    actor = {"user_id": str(owner_id)}

    async def authenticated(_request):
        return None, None, actor

    monkeypatch.setattr(workspace_member_routes, "_authenticated", authenticated)
    monkeypatch.setattr(workspace_member_routes, "_check_csrf", lambda _request, _session: None)
    app.state.db_pool = pool
    app.state.auth_store = AuthStore(pool)

    try:
        async with pool.acquire() as connection:
            await connection.executemany(
                """INSERT INTO app_users
                   (id,email,password_hash,status,email_verified_at)
                   VALUES ($1,$2,'integration-test-hash','active',now())""",
                [
                    (user_id, f"{user_id.hex}-{label}@member-role.example")
                    for user_id, label in users
                ],
            )
            await connection.execute(
                "INSERT INTO workspaces (id,name) VALUES ($1,$2),($3,$4)",
                workspace_id, "Membership role acceptance",
                other_workspace_id, "Outsider workspace",
            )
            await connection.executemany(
                """INSERT INTO workspace_memberships (workspace_id,user_id,role,status)
                   VALUES ($1,$2,$3,'active')""",
                [
                    (workspace_id, owner_id, "owner"),
                    (workspace_id, admin_id, "admin"),
                    (workspace_id, member_id, "member"),
                    (workspace_id, second_admin_id, "admin"),
                    (other_workspace_id, outsider_id, "owner"),
                ],
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # An admin cannot grant another member admin privileges.
            actor["user_id"] = str(admin_id)
            denied_promotion = await client.patch(
                f"/api/v1/workspaces/members/{member_id}",
                json={"workspace_id": workspace_id, "role": "admin"},
            )
            assert denied_promotion.status_code == 403
            assert denied_promotion.json()["detail"] == "only_owner_can_grant_admin"

            # An admin cannot change or remove a peer admin.
            denied_peer_change = await client.patch(
                f"/api/v1/workspaces/members/{second_admin_id}",
                json={"workspace_id": workspace_id, "role": "viewer"},
            )
            assert denied_peer_change.status_code == 403
            assert denied_peer_change.json()["detail"] == "only_owner_can_change_admin"

            denied_peer_removal = await client.delete(
                f"/api/v1/workspaces/members/{second_admin_id}?workspace_id={workspace_id}"
            )
            assert denied_peer_removal.status_code == 403
            assert denied_peer_removal.json()["detail"] == "only_owner_can_remove_admin"

            # A tenant admin cannot mutate a user who is not a member of that tenant.
            denied_cross_tenant = await client.patch(
                f"/api/v1/workspaces/members/{outsider_id}",
                json={"workspace_id": workspace_id, "role": "viewer"},
            )
            assert denied_cross_tenant.status_code == 404
            assert denied_cross_tenant.json()["detail"] == "workspace_member_not_found"

            # The owner can promote a verified active member and the change is audited.
            actor["user_id"] = str(owner_id)
            promoted = await client.patch(
                f"/api/v1/workspaces/members/{member_id}",
                json={"workspace_id": workspace_id, "role": "admin"},
            )
            assert promoted.status_code == 200, promoted.text
            assert promoted.json()["role"] == "admin"

            # The owner can revoke the promoted member and its audit event is persisted.
            removed = await client.delete(
                f"/api/v1/workspaces/members/{member_id}?workspace_id={workspace_id}"
            )
            assert removed.status_code == 200, removed.text
            assert removed.json()["removed"] is True

            # The owner role is protected even from the current owner.
            protected_owner = await client.delete(
                f"/api/v1/workspaces/members/{owner_id}?workspace_id={workspace_id}"
            )
            assert protected_owner.status_code == 409
            assert protected_owner.json()["detail"] == "workspace_owner_cannot_be_removed"

        async with pool.acquire() as connection:
            member_state = await connection.fetchrow(
                """SELECT role,status FROM workspace_memberships
                   WHERE workspace_id=$1 AND user_id=$2""",
                workspace_id, member_id,
            )
            assert member_state["role"] == "admin"
            assert member_state["status"] == "revoked"

            peer_admin_state = await connection.fetchrow(
                """SELECT role,status FROM workspace_memberships
                   WHERE workspace_id=$1 AND user_id=$2""",
                workspace_id, second_admin_id,
            )
            assert peer_admin_state["role"] == "admin"
            assert peer_admin_state["status"] == "active"

            role_audit = await connection.fetchval(
                """SELECT count(*) FROM security_audit_events
                   WHERE workspace_id=$1 AND actor_user_id=$2
                     AND event_type='workspace.member.role_changed'
                     AND metadata->>'target_user_id'=$3
                     AND metadata->>'role'='admin'""",
                workspace_id, owner_id, str(member_id),
            )
            removal_audit = await connection.fetchval(
                """SELECT count(*) FROM security_audit_events
                   WHERE workspace_id=$1 AND actor_user_id=$2
                     AND event_type='workspace.member.removed'
                     AND metadata->>'target_user_id'=$3""",
                workspace_id, owner_id, str(member_id),
            )
            assert role_audit == 1
            assert removal_audit == 1
    finally:
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM workspaces WHERE id=ANY($1::text[])",
                [workspace_id, other_workspace_id],
            )
            await connection.execute(
                "DELETE FROM app_users WHERE id=ANY($1::uuid[])",
                [user_id for user_id, _label in users],
            )
        await pool.close()
        app.state.db_pool = previous_pool
        app.state.auth_store = previous_auth_store
