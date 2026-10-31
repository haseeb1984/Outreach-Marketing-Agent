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


def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL on semicolons outside strings, comments and PostgreSQL dollar quotes."""
    statements: list[str] = []
    start = 0
    i = 0
    state = "normal"
    dollar_tag: str | None = None
    while i < len(sql):
        if state == "single":
            if sql[i] == "'" and i + 1 < len(sql) and sql[i + 1] == "'":
                i += 2
                continue
            if sql[i] == "'":
                state = "normal"
            elif sql[i] == "\\\\" and i + 1 < len(sql):
                i += 2
                continue
        elif state == "double":
            if sql[i] == '"' and i + 1 < len(sql) and sql[i + 1] == '"':
                i += 2
                continue
            if sql[i] == '"':
                state = "normal"
        elif state == "line_comment":
            if sql[i] == "\n":
                state = "normal"
        elif state == "block_comment":
            if sql.startswith("*/", i):
                state = "normal"
                i += 2
                continue
        elif state == "dollar":
            if sql.startswith(dollar_tag or "", i):
                i += len(dollar_tag or "")
                state = "normal"
                continue
        else:
            if sql.startswith("--", i):
                state = "line_comment"
                i += 2
                continue
            if sql.startswith("/*", i):
                state = "block_comment"
                i += 2
                continue
            if sql[i] == "'":
                state = "single"
            elif sql[i] == '"':
                state = "double"
            elif sql[i] == "$":
                end = sql.find("$", i + 1)
                if end >= 0:
                    tag = sql[i:end + 1]
                    if all(ch.isalnum() or ch == "_" for ch in tag[1:-1]):
                        dollar_tag = tag
                        state = "dollar"
                        i = end + 1
                        continue
            elif sql[i] == ";":
                statement = sql[start:i + 1].strip()
                if statement:
                    statements.append(statement)
                start = i + 1
        i += 1
    trailing = sql[start:].strip()
    if trailing:
        statements.append(trailing)
    if state in {"single", "double", "block_comment", "dollar"}:
        raise ValueError("migration_sql_unterminated_literal_or_comment")
    return statements


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
                try:
                    statements = _split_sql_statements(sql)
                    if not statements:
                        raise ValueError("migration_sql_empty")
                    for statement in statements:
                        await connection.execute(statement)
                except Exception as exc:
                    raise RuntimeError(f"Migration failed: {path.name}") from exc
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
