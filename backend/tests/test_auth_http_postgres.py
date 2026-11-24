"""HTTP + PostgreSQL acceptance for verification and password-reset endpoints.

These tests exercise the FastAPI routes against the same real AuthStore/PostgreSQL
pool used by the application. SMTP delivery is intentionally outside this
acceptance boundary; tokens are obtained from the store for deterministic tests.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.db.migrations import apply_migrations
from app.main import app
from app.services.auth_store import AuthStore


class AllowLimiter:
    async def consume(self, **kwargs):
        return {
            "allowed": True,
            "remaining": 9,
            "reset_at": datetime.now(timezone.utc) + timedelta(minutes=15),
        }


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_email_verification_http_endpoint_persists_verified_state(monkeypatch):
    asyncio.run(_exercise_email_verification_http(monkeypatch))


async def _exercise_email_verification_http(monkeypatch):
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)
    store = AuthStore(pool)
    email = f"verify-http-{uuid4().hex}@example.test"
    created = None
    try:
        created = await store.register_user(
            email=email, password="verification-http-password-123"
        )
        assert created is not None
        monkeypatch.setattr(
            "app.api.auth_routes.settings.frontend_origins",
            "https://app.example.test",
        )
        app.state.auth_store = store
        app.state.auth_rate_limiter = AllowLimiter()
        with TestClient(app, base_url="https://app.example.test") as client:
            response = client.post(
                "/api/v1/auth/verify-email",
                headers={"Origin": "https://app.example.test"},
                json={"token": created["verification_token"]},
            )
            assert response.status_code == 200
            assert response.json()["message"] == "Email verified. You can now sign in."

            replay = client.post(
                "/api/v1/auth/verify-email",
                headers={"Origin": "https://app.example.test"},
                json={"token": created["verification_token"]},
            )
            assert replay.status_code == 400

        async with pool.acquire() as connection:
            state = await connection.fetchrow(
                "SELECT status,email_verified_at FROM app_users WHERE id=$1",
                created["user_id"],
            )
            assert state["status"] == "active"
            assert state["email_verified_at"] is not None
            event_count = await connection.fetchval(
                """SELECT count(*) FROM security_audit_events
                   WHERE workspace_id=$1 AND actor_user_id=$2
                     AND event_type='account.email_verified' AND outcome='success'""",
                created["workspace_id"], created["user_id"],
            )
            assert event_count == 1
    finally:
        if created is not None:
            async with pool.acquire() as connection:
                await connection.execute(
                    "DELETE FROM workspaces WHERE id=$1", created["workspace_id"]
                )
                await connection.execute(
                    "DELETE FROM app_users WHERE id=$1", created["user_id"]
                )
        await pool.close()


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_password_reset_http_endpoint_changes_password_and_invalidates_sessions(monkeypatch):
    asyncio.run(_exercise_password_reset_http(monkeypatch))


async def _exercise_password_reset_http(monkeypatch):
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=4)
    store = AuthStore(pool)
    email = f"reset-http-{uuid4().hex}@example.test"
    created = None
    try:
        created = await store.register_user(
            email=email, password="reset-http-original-password-123"
        )
        assert created is not None
        assert await store.verify_email(created["verification_token"]) is True
        session = await store.create_session(user_id=created["user_id"])
        reset = await store.issue_password_reset(email=email)
        assert reset is not None

        monkeypatch.setattr(
            "app.api.auth_routes.settings.frontend_origins",
            "https://app.example.test",
        )
        app.state.auth_store = store
        app.state.auth_rate_limiter = AllowLimiter()
        with TestClient(app, base_url="https://app.example.test") as client:
            response = client.post(
                "/api/v1/auth/password-reset/confirm",
                headers={"Origin": "https://app.example.test"},
                json={
                    "token": reset["reset_token"],
                    "new_password": "reset-http-new-password-456",
                },
            )
            assert response.status_code == 200
            assert response.json()["message"] == (
                "Password updated. Sign in again with your new password."
            )

            replay = client.post(
                "/api/v1/auth/password-reset/confirm",
                headers={"Origin": "https://app.example.test"},
                json={
                    "token": reset["reset_token"],
                    "new_password": "reset-http-another-password-789",
                },
            )
            assert replay.status_code == 400

        assert await store.authenticate_password(
            email=email, password="reset-http-original-password-123"
        ) is None
        assert await store.authenticate_password(
            email=email, password="reset-http-new-password-456"
        ) is not None
        assert await store.authenticate_session(session["token"]) is None

        async with pool.acquire() as connection:
            consumed = await connection.fetchval(
                """SELECT consumed_at FROM password_reset_tokens
                   WHERE user_id=$1 ORDER BY created_at DESC LIMIT 1""",
                created["user_id"],
            )
            assert consumed is not None
            event_count = await connection.fetchval(
                """SELECT count(*) FROM security_audit_events
                   WHERE actor_user_id=$1 AND event_type='account.password_reset'
                     AND outcome='success'""",
                created["user_id"],
            )
            assert event_count == 1
    finally:
        if created is not None:
            async with pool.acquire() as connection:
                await connection.execute(
                    "DELETE FROM workspaces WHERE id=$1", created["workspace_id"]
                )
                await connection.execute(
                    "DELETE FROM app_users WHERE id=$1", created["user_id"]
                )
        await pool.close()
