"""Explicit, transactional PostgreSQL migration runner.

Run from the backend directory with DATABASE_URL configured:
    python -m app.db.migrations
This is never executed automatically during API startup.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from app.core.config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
MIGRATION_LOCK_KEY = "outreach-marketing-agent:migrations"


async def apply_migrations(database_url: str, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply unapplied SQL migrations in filename order and record each transactionally."""
    if not database_url or not database_url.strip():
        raise ValueError("DATABASE_URL is required to apply database migrations")
    if not migrations_dir.is_dir():
        raise ValueError(f"Migration directory does not exist: {migrations_dir}")

    applied: list[str] = []
    connection = await asyncpg.connect(database_url, timeout=5, command_timeout=30)
    try:
        await connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version TEXT PRIMARY KEY,
                   applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
               )"""
        )
        # Use a transaction-scoped lock inside each migration transaction. A
        # session-level lock may not survive transaction-pooling PostgreSQL URLs.
        for path in sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql")):
            async with connection.transaction():
                await connection.fetchval(
                    "SELECT pg_advisory_xact_lock(hashtext($1))",
                    MIGRATION_LOCK_KEY,
                )
                exists = await connection.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version=$1)",
                    path.name,
                )
                if exists:
                    continue
                sql = path.read_text(encoding="utf-8")
                if not sql.strip():
                    raise ValueError(f"Migration is empty: {path.name}")
                await connection.execute(sql)
                await connection.execute(
                    "INSERT INTO schema_migrations(version) VALUES($1)", path.name
                )
                applied.append(path.name)
    finally:
        await connection.close()
    return applied


async def _main() -> None:
    applied = await apply_migrations(settings.database_url or "")
    if applied:
        print("Applied migrations: " + ", ".join(applied))
    else:
        print("Database schema is already up to date.")


if __name__ == "__main__":
    asyncio.run(_main())
