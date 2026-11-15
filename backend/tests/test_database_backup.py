import hashlib
from pathlib import Path

import pytest

from scripts import database_backup


def test_connection_url_is_translated_to_environment_not_command_arguments(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "not-used")
    env = database_backup._connection_environment(
        "postgresql://oma_user:p%40ssword@db.example:5433/oma?sslmode=require"
    )
    assert env["PGHOST"] == "db.example"
    assert env["PGPORT"] == "5433"
    assert env["PGDATABASE"] == "oma"
    assert env["PGUSER"] == "oma_user"
    assert env["PGPASSWORD"] == "p@ssword"
    assert env["PGSSLMODE"] == "require"


@pytest.mark.parametrize("url", ["", "https://example.com/db", "postgresql:///missing-host", "postgresql://db.example/"])
def test_connection_url_requires_postgres_host_and_database(url):
    with pytest.raises(ValueError):
        database_backup._connection_environment(url)


def test_verify_rejects_checksum_mismatch_before_calling_postgres_tools(tmp_path, monkeypatch):
    backup = tmp_path / "sample.dump"
    backup.write_bytes(b"backup bytes")
    backup.with_suffix(".dump.sha256").write_text("0" * 64 + "  sample.dump\n")
    monkeypatch.setattr(database_backup, "_run", lambda *_args, **_kwargs: pytest.fail("tool must not run"))

    with pytest.raises(ValueError, match="checksum_mismatch"):
        database_backup.verify(backup)


def test_restore_refuses_the_source_database_as_target(tmp_path, monkeypatch):
    backup = tmp_path / "sample.dump"
    backup.write_bytes(b"backup bytes")
    backup.with_suffix(".dump.sha256").write_text(hashlib.sha256(b"backup bytes").hexdigest() + "  sample.dump\n")
    monkeypatch.setattr(database_backup, "_run", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("SOURCE_DATABASE_URL", "postgresql://user:secret@db.example:5432/prod")
    monkeypatch.setenv("RESTORE_DATABASE_URL", "postgresql://other:secret@db.example:5432/prod")
    monkeypatch.setenv("CONFIRM_RESTORE", "YES")

    with pytest.raises(ValueError, match="must_differ"):
        database_backup.restore(backup)


def test_restore_requires_explicit_confirmation_and_uses_dbname_flag(tmp_path, monkeypatch):
    backup = tmp_path / "sample.dump"
    backup.write_bytes(b"backup bytes")
    backup.with_suffix(".dump.sha256").write_text(hashlib.sha256(b"backup bytes").hexdigest() + "  sample.dump\n")
    calls = []
    monkeypatch.setattr(database_backup, "_run", lambda command, env: calls.append((command, env)))
    monkeypatch.setenv("SOURCE_DATABASE_URL", "postgresql://user:secret@source.example:5432/prod")
    monkeypatch.setenv("RESTORE_DATABASE_URL", "postgresql://user:secret@restore.example:5432/recovery")
    monkeypatch.delenv("CONFIRM_RESTORE", raising=False)

    with pytest.raises(ValueError, match="CONFIRM_RESTORE"):
        database_backup.restore(backup)
    monkeypatch.setenv("CONFIRM_RESTORE", "YES")
    database_backup.restore(backup)

    assert len(calls) == 3
    restore_command, restore_env = calls[2]
    assert restore_command[0] == "pg_restore"
    assert "--dbname" in restore_command
    assert "--single-transaction" in restore_command
    assert "secret" not in " ".join(restore_command)
    assert restore_env["PGPASSWORD"] == "secret"


def test_verify_rejects_empty_checksum_sidecar(tmp_path, monkeypatch):
    backup = tmp_path / "sample.dump"
    backup.write_bytes(b"backup bytes")
    backup.with_suffix(".dump.sha256").write_text("  \n")
    monkeypatch.setattr(database_backup, "_run", lambda *_args, **_kwargs: pytest.fail("tool must not run"))

    with pytest.raises(ValueError, match="checksum_invalid"):
        database_backup.verify(backup)
