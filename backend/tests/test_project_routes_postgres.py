"""Project API lifecycle and tenant-scoping coverage against disposable PostgreSQL."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import httpx
import pytest

from app.db.migrations import apply_migrations
from app.main import app
from app.api import project_routes


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_project_api_lifecycle_is_persisted_and_workspace_scoped(monkeypatch):
    asyncio.run(_exercise_project_lifecycle(monkeypatch))


async def _exercise_project_lifecycle(monkeypatch) -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)

    user_id = uuid4()
    workspace_a = "project-integration-a-" + user_id.hex
    workspace_b = "project-integration-b-" + user_id.hex
    previous_pool = getattr(app.state, "db_pool", None)
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)

    async def authenticated(_request):
        return (
            f"{user_id.hex}@project-integration.example",
            None,
            {"user_id": str(user_id)},
        )

    async def authorize(_request, workspace_id, _minimum_role, session):
        assert session["user_id"] == str(user_id)
        assert workspace_id in {workspace_a, workspace_b}

    monkeypatch.setattr(project_routes, "_authenticated", authenticated)
    monkeypatch.setattr(project_routes, "_check_csrf", lambda _request, _session: None)
    monkeypatch.setattr(project_routes, "_authorize", authorize)
    app.state.db_pool = pool

    try:
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO app_users (id,email,password_hash,status,email_verified_at)
                   VALUES ($1,$2,'integration-test-hash','active',now())""",
                user_id,
                f"{user_id.hex}@project-integration.example",
            )
            await connection.execute(
                "INSERT INTO workspaces (id,name) VALUES ($1,$2),($3,$4)",
                workspace_a,
                "Project Integration A",
                workspace_b,
                "Project Integration B",
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            headers = {"x-csrf-token": "project-integration-csrf"}

            created_a = await client.post(
                "/api/v1/projects",
                headers=headers,
                json={
                    "workspace_id": workspace_a,
                    "name": "Workspace A website",
                    "website_url": "https://workspace-a.example",
                    "competitors": ["https://competitor-a.example"],
                },
            )
            created_b = await client.post(
                "/api/v1/projects",
                headers=headers,
                json={
                    "workspace_id": workspace_b,
                    "name": "Workspace B website",
                    "website_url": "https://workspace-b.example",
                },
            )

            assert created_a.status_code == 201, created_a.text
            assert created_b.status_code == 201, created_b.text
            project_a_id = created_a.json()["id"]
            project_b_id = created_b.json()["id"]

            listed_a = await client.get(
                "/api/v1/projects", params={"workspace_id": workspace_a}
            )
            assert listed_a.status_code == 200, listed_a.text
            assert [item["id"] for item in listed_a.json()["items"]] == [project_a_id]

            cross_workspace_update = await client.patch(
                f"/api/v1/projects/{project_a_id}",
                headers=headers,
                json={"workspace_id": workspace_b, "name": "Cross-tenant overwrite"},
            )
            assert cross_workspace_update.status_code == 404

            updated_a = await client.patch(
                f"/api/v1/projects/{project_a_id}",
                headers=headers,
                json={"workspace_id": workspace_a, "name": "Workspace A updated"},
            )
            assert updated_a.status_code == 200, updated_a.text
            assert updated_a.json()["name"] == "Workspace A updated"

            cross_workspace_archive = await client.delete(
                f"/api/v1/projects/{project_b_id}",
                headers=headers,
                params={"workspace_id": workspace_a},
            )
            assert cross_workspace_archive.status_code == 404

            archived_a = await client.delete(
                f"/api/v1/projects/{project_a_id}",
                headers=headers,
                params={"workspace_id": workspace_a},
            )
            assert archived_a.status_code == 204

            after_archive = await client.get(
                "/api/v1/projects", params={"workspace_id": workspace_a}
            )
            assert after_archive.status_code == 200, after_archive.text
            assert after_archive.json()["items"] == []

    finally:
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM workspaces WHERE id=ANY($1::text[])",
                [workspace_a, workspace_b],
            )
            await connection.execute(
                "DELETE FROM app_users WHERE id=$1",
                user_id,
            )
        await pool.close()
        app.state.db_pool = previous_pool
