import hashlib
from pathlib import Path
from types import SimpleNamespace

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
    monkeypatch.setattr(database_backup.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="f\\n"))
    monkeypatch.setenv("SOURCE_DATABASE_URL", "postgresql://user:secret@source.example:5432/prod")
    monkeypatch.setenv("RESTORE_DATABASE_URL", "postgresql://user:secret@restore.example:5432/recovery")
    monkeypatch.delenv("CONFIRM_RESTORE", raising=False)

    with pytest.raises(ValueError, match="CONFIRM_RESTORE"):
        database_backup.restore(backup)
    monkeypatch.setenv("CONFIRM_RESTORE", "YES")
    database_backup.restore(backup)

    assert len(calls) == 2
    restore_command, restore_env = calls[1]
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



def test_prune_is_dry_run_by_default_and_preserves_minimum(tmp_path):
    import os
    import time

    now = time.time()
    backups = []
    for index in range(4):
        path = tmp_path / f"outreach-db-2026010{index + 1}T000000Z.dump"
        path.write_bytes(b"archive")
        path.with_suffix(".dump.sha256").write_text("checksum")
        os.utime(path, (now - (10 - index) * 86400, now - (10 - index) * 86400))
        backups.append(path)
    unrelated = tmp_path / "customer-export.dump"
    unrelated.write_bytes(b"keep")

    candidates = database_backup.prune(tmp_path, older_than_days=5, keep_at_least=2)
    assert len(candidates) == 2
    assert all(path.exists() for path in backups)
    assert unrelated.exists()


def test_prune_apply_removes_only_expired_archives_and_sidecars(tmp_path):
    import os
    import time

    now = time.time()
    backups = []
    for index in range(4):
        path = tmp_path / f"outreach-db-2026010{index + 1}T000000Z.dump"
        path.write_bytes(b"archive")
        path.with_suffix(".dump.sha256").write_text("checksum")
        os.utime(path, (now - (10 - index) * 86400, now - (10 - index) * 86400))
        backups.append(path)
    unrelated = tmp_path / "outreach-db-not-a-backup.txt"
    unrelated.write_text("keep")

    removed = database_backup.prune(tmp_path, older_than_days=5, keep_at_least=2, apply=True)
    assert len(removed) == 2
    assert not backups[0].exists() and not backups[1].exists()
    assert not backups[0].with_suffix(".dump.sha256").exists()
    assert backups[2].exists() and backups[3].exists()
    assert unrelated.exists()


@pytest.mark.parametrize("days,keep", [(0, 2), (30, 0), (-1, 1)])
def test_prune_rejects_unsafe_retention_values(tmp_path, days, keep):
    with pytest.raises(ValueError):
        database_backup.prune(tmp_path, older_than_days=days, keep_at_least=keep, apply=True)


def test_prune_ignores_symlinked_backup_files(tmp_path):
    import os
    import time

    source = tmp_path / "outside.dump"
    source.write_bytes(b"do not delete")
    link = tmp_path / "outreach-db-20260101T000000Z.dump"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")
    old = time.time() - 10 * 86400
    os.utime(link, (old, old), follow_symlinks=False)
    database_backup.prune(tmp_path, older_than_days=5, keep_at_least=1, apply=True)
    assert source.exists()
    assert link.is_symlink()


def test_backup_writes_private_archive_and_checksum_atomically(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://backup-user:backup-pass@db.example:5432/outreach")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    calls = []

    def fake_run(command, environment):
        calls.append((command, environment))
        if command[0] == "pg_dump":
            output_index = command.index("--file") + 1
            Path(command[output_index]).write_bytes(b"verified backup archive")

    monkeypatch.setattr(database_backup, "_run", fake_run)
    result = database_backup.backup()

    assert result.parent == tmp_path
    assert result.name.startswith("outreach-db-") and result.suffix == ".dump"
    assert result.read_bytes() == b"verified backup archive"
    checksum_file = result.with_suffix(".dump.sha256")
    expected = hashlib.sha256(b"verified backup archive").hexdigest()
    assert checksum_file.read_text(encoding="utf-8") == f"{expected}  {result.name}\\n"
    assert result.stat().st_mode & 0o777 == 0o600
    assert checksum_file.stat().st_mode & 0o777 == 0o600
    assert len(calls) == 2
    assert calls[0][0][:3] == ["pg_dump", "--format=custom", "--no-owner"]
    assert calls[0][1]["PGPASSWORD"] == "backup-pass"
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([result.name, checksum_file.name])


def test_backup_failure_removes_temporary_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://backup-user:backup-pass@db.example:5432/outreach")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))

    def failed_dump(command, environment):
        Path(command[command.index("--file") + 1]).write_bytes(b"partial")
        raise RuntimeError("simulated pg_dump failure")

    monkeypatch.setattr(database_backup, "_run", failed_dump)
    with pytest.raises(RuntimeError, match="simulated pg_dump failure"):
        database_backup.backup()

    assert list(tmp_path.iterdir()) == []
