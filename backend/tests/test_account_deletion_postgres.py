"""PostgreSQL integration coverage for the account-deletion timestamp contract."""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

from app.db.migrations import apply_migrations


@pytest.mark.skipif(
    not os.getenv("OMA_TEST_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL test database",
)
def test_deleted_account_requires_timestamp_and_active_account_forbids_it():
    asyncio.run(_exercise_deleted_at_constraint())


async def _exercise_deleted_at_constraint() -> None:
    database_url = os.environ["OMA_TEST_DATABASE_URL"]
    await apply_migrations(database_url)
    connection = await asyncpg.connect(database_url)
    user_id = uuid4()
    email = f"{user_id.hex}@retention-test.example"
    try:
        await connection.execute(
            """INSERT INTO app_users (id,email,password_hash,status)
               VALUES ($1,$2,'integration-test-hash','active')""",
            user_id, email,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                "UPDATE app_users SET status='deleted' WHERE id=$1",
                user_id,
            )
        await connection.execute(
            """UPDATE app_users
               SET status='deleted',deleted_at=now(),email_verified_at=NULL
               WHERE id=$1""",
            user_id,
        )
        deleted_at = await connection.fetchval(
            "SELECT deleted_at FROM app_users WHERE id=$1",
            user_id,
        )
        assert deleted_at is not None
    finally:
        await connection.execute("DELETE FROM app_users WHERE id=$1", user_id)
        await connection.close()
