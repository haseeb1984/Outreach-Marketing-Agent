"""HTTP-level PostgreSQL tenant-isolation acceptance for the prospect CRM.

Runs against the dedicated disposable OMA_TEST_DATABASE_URL database. Unlike the
unit tests with fake stores, this exercises real sessions, membership authorization,
the FastAPI route, and workspace-filtered PostgreSQL persistence together.
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest
import httpx

from app.api.auth_routes import cookie_policy
from app.db.migrations import apply_migrations
from app.main import app
from app.services.auth_store import AuthStore
from app.services.auth_security import hash_password
from app.services.prospect_store import ProspectStore


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_authenticated_prospect_http_routes_enforce_real_tenant_isolation():
    asyncio.run(_exercise_authenticated_prospect_tenant_isolation())


async def _exercise_authenticated_prospect_tenant_isolation() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    user_a, user_b = uuid4(), uuid4()
    workspace_a = "http-tenant-a-" + uuid4().hex
    workspace_b = "http-tenant-b-" + uuid4().hex
    prospect_a, prospect_b = "Tenant A private prospect", "Tenant B private prospect"

    connection = await asyncpg.connect(database_url)
    try:
        await apply_migrations(database_url)
        await connection.execute(
            """INSERT INTO app_users (id,email,password_hash,email_verified_at,status)
               VALUES ($1,$2,$3,now(),'active'),($4,$5,$3,now(),'active')""",
            user_a, f"{user_a.hex}@example.test",
            hash_password("tenant-isolation-integration-password").encoded,
            user_b, f"{user_b.hex}@example.test",
        )
        await connection.execute(
            "INSERT INTO workspaces (id,name) VALUES ($1,'Tenant A'),($2,'Tenant B')",
            workspace_a, workspace_b,
        )
        await connection.execute(
            """INSERT INTO workspace_memberships (workspace_id,user_id,role,status)
               VALUES ($1,$2,'owner','active'),($3,$4,'owner','active')""",
            workspace_a, user_a, workspace_b, user_b,
        )

        async def seed_prospect(workspace_id: str, creator_id, name: str) -> None:
            await connection.execute(
                """INSERT INTO crm_prospects
                   (workspace_id,created_by,name,company,website_url,evidence_url,fit_reason)
                   VALUES ($1,$2,$3,'Private Integration Co','https://example.test/',
                           'https://example.test/evidence','Tenant isolation fixture')""",
                workspace_id, creator_id, name,
            )

        await seed_prospect(workspace_a, user_a, prospect_a)
        await seed_prospect(workspace_b, user_b, prospect_b)
    finally:
        await connection.close()

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
    try:
        auth_store = AuthStore(pool)
        session = await auth_store.create_session(user_id=user_a, lifetime_hours=1)

        # ASGITransport keeps requests on this same event loop as asyncpg's pool.
        # No TestClient thread or fake authorization/persistence layer is involved.
        app.state.auth_store = auth_store
        app.state.prospect_store = ProspectStore(pool)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://app.example.test"
        ) as client:
            client.cookies.set(cookie_policy.name, session["token"])
            own_response = await client.get(
                "/api/v1/prospects", params={"workspace_id": workspace_a}
            )
            assert own_response.status_code == 200
            own_items = own_response.json()["items"]
            assert [item["name"] for item in own_items] == [prospect_a]
            assert all(item["workspace_id"] == workspace_a for item in own_items)

            foreign_response = await client.get(
                "/api/v1/prospects", params={"workspace_id": workspace_b}
            )
            assert foreign_response.status_code == 404
            assert foreign_response.json()["detail"] == "workspace_not_found"
            assert prospect_b not in foreign_response.text
    finally:
        await pool.close()
        cleanup = await asyncpg.connect(database_url)
        try:
            await cleanup.execute(
                "DELETE FROM workspaces WHERE id = ANY($1::text[])",
                [workspace_a, workspace_b],
            )
            await cleanup.execute(
                "DELETE FROM app_users WHERE id = ANY($1::uuid[])",
                [user_a, user_b],
            )
        finally:
            await cleanup.close()
