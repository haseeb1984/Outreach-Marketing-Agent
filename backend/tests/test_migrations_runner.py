from __future__ import annotations

from pathlib import Path

import pytest

from app.db import migrations


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self, applied: set[str] | None = None):
        self.applied = set(applied or ())
        self.executed_sql: list[str] = []
        self.closed = False

    def transaction(self):
        return _Transaction()

    async def fetchval(self, query: str, *args):
        if "pg_advisory_xact_lock" in query:
            return None
        if "SELECT EXISTS" in query and "schema_migrations" in query:
            return args[0] in self.applied
        raise AssertionError(f"Unexpected fetchval query: {query}")

    async def execute(self, query: str, *args):
        if query.startswith("INSERT INTO schema_migrations"):
            self.applied.add(args[0])
            return "INSERT 0 1"
        if query.startswith("CREATE TABLE IF NOT EXISTS schema_migrations"):
            return "CREATE TABLE"
        self.executed_sql.append(query)
        return "OK"

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_runner_applies_pending_migrations_in_filename_order_and_records_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "003_third.sql").write_text("SELECT 'third';", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 'first';", encoding="utf-8")
    (tmp_path / "002_second.sql").write_text("SELECT 'second';", encoding="utf-8")
    connection = _FakeConnection()

    async def fake_connect(database_url: str, **kwargs):
        assert database_url == "postgresql://test.invalid/db"
        assert kwargs["timeout"] == 5
        return connection

    monkeypatch.setattr(migrations.asyncpg, "connect", fake_connect)

    applied = await migrations.apply_migrations(
        "postgresql://test.invalid/db", migrations_dir=tmp_path
    )

    assert applied == ["001_first.sql", "002_second.sql", "003_third.sql"]
    assert connection.applied == set(applied)
    assert connection.executed_sql == [
        "SELECT 'first';",
        "SELECT 'second';",
        "SELECT 'third';",
    ]
    assert connection.closed


@pytest.mark.asyncio
async def test_runner_skips_migrations_already_in_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "001_already_applied.sql").write_text(
        "SELECT 'should not run';", encoding="utf-8"
    )
    (tmp_path / "002_pending.sql").write_text("SELECT 'pending';", encoding="utf-8")
    connection = _FakeConnection({"001_already_applied.sql"})

    async def fake_connect(database_url: str, **kwargs):
        return connection

    monkeypatch.setattr(migrations.asyncpg, "connect", fake_connect)

    applied = await migrations.apply_migrations(
        "postgresql://test.invalid/db", migrations_dir=tmp_path
    )

    assert applied == ["002_pending.sql"]
    assert connection.executed_sql == ["SELECT 'pending';"]
    assert connection.applied == {"001_already_applied.sql", "002_pending.sql"}
    assert connection.closed


@pytest.mark.asyncio
async def test_runner_rejects_missing_database_url_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def unexpected_connect(*args, **kwargs):
        raise AssertionError("connect must not be called without DATABASE_URL")

    monkeypatch.setattr(migrations.asyncpg, "connect", unexpected_connect)

    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        await migrations.apply_migrations("", migrations_dir=tmp_path)
