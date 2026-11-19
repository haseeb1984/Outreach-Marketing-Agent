"""End-to-end account export coverage against a disposable migrated PostgreSQL database."""
from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import asyncpg
import pytest
import httpx

from app.api import account_routes
from app.db.migrations import apply_migrations
from app.main import app


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_account_export_is_tenant_scoped_and_excludes_authentication_secrets(monkeypatch):
    asyncio.run(_exercise_account_export(monkeypatch))


async def _exercise_account_export(monkeypatch) -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)

    user_id = uuid4()
    other_user_id = uuid4()
    workspace_id = "privacy-export-" + user_id.hex
    other_workspace_id = "privacy-export-other-" + user_id.hex
    private_password_marker = "DO_NOT_EXPORT_PASSWORD_HASH_" + user_id.hex
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)

    async def authenticated(_request):
        return (
            f"{user_id.hex}@privacy-export.example",
            None,
            {"user_id": str(user_id)},
        )

    monkeypatch.setattr(account_routes, "_authenticated", authenticated)

    try:
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO app_users (id,email,password_hash,status,email_verified_at)
                   VALUES ($1,$2,$3,'active',now()),($4,$5,'other-test-hash','active',now())""",
                user_id,
                f"{user_id.hex}@privacy-export.example",
                private_password_marker,
                other_user_id,
                f"{other_user_id.hex}@privacy-export-other.example",
            )
            await connection.execute(
                "INSERT INTO workspaces (id,name) VALUES ($1,$2),($3,$4)",
                workspace_id,
                "Export Test Workspace",
                other_workspace_id,
                "Private Other Workspace",
            )
            await connection.execute(
                """INSERT INTO workspace_memberships (workspace_id,user_id,role,status)
                   VALUES ($1,$2,'owner','active'),($3,$4,'owner','active')""",
                workspace_id,
                user_id,
                other_workspace_id,
                other_user_id,
            )
            await connection.execute(
                """INSERT INTO workspace_domains
                   (workspace_id,domain_ascii,status,verification_method,verified_at)
                   VALUES ($1,'export-visible.example','verified','dns_txt',now()),
                          ($2,'must-not-leak.example','verified','dns_txt',now())""",
                workspace_id,
                other_workspace_id,
            )
            await connection.execute(
                """INSERT INTO auth_sessions (user_id,token_sha256,expires_at)
                   VALUES ($1,$2,now()+interval '1 day')""",
                user_id,
                ("a" * 64),
            )

        app.state.db_pool = pool
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/account/export")

        assert response.status_code == 200, response.text
        assert response.headers["content-disposition"].startswith("attachment;")
        assert response.headers["cache-control"] == "no-store, private"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"

        payload = response.json()
        assert payload["account"]["email"] == f"{user_id.hex}@privacy-export.example"
        assert [row["workspace_id"] for row in payload["workspaces"]] == [workspace_id]
        assert [row["domain_ascii"] for row in payload["domains"]] == ["export-visible.example"]
        assert payload["limits"]["truncated_collections"] == []
        assert payload["limits"]["not_included_collections"] == []

        serialized = json.dumps(payload, sort_keys=True)
        assert private_password_marker not in serialized
        assert "other-test-hash" not in serialized
        assert "must-not-leak.example" not in serialized
        assert "token_sha256" not in serialized
        assert "auth_sessions" not in serialized
        assert "Private Other Workspace" not in serialized
    finally:
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM workspaces WHERE id=ANY($1::text[])",
                [workspace_id, other_workspace_id],
            )
            await connection.execute(
                "DELETE FROM app_users WHERE id=ANY($1::uuid[])",
                [user_id, other_user_id],
            )
        await pool.close()
