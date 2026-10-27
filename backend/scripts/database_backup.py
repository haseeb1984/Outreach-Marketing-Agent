"""Explicit PostgreSQL backup/verification/restore tools.

Examples (run from backend/):
  python scripts/database_backup.py backup
  python scripts/database_backup.py verify /path/to/backup.dump
  CONFIRM_RESTORE=YES RESTORE_DATABASE_URL=postgresql://... python scripts/database_backup.py restore /path/to/backup.dump

The restore target must be a separately provisioned, empty recovery/staging database.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


_ALLOWED_QUERY_ENV = {
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "application_name": "PGAPPNAME",
    "channel_binding": "PGCHANNELBINDING",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
}


def _connection_environment(url: str) -> dict[str, str]:
    """Translate a PostgreSQL URL into libpq environment variables, not argv."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise ValueError("invalid_database_url")
    if not parsed.path or parsed.path == "/":
        raise ValueError("database_name_required")
    environment = dict(os.environ)
    environment["PGHOST"] = parsed.hostname
    environment["PGPORT"] = str(parsed.port or 5432)
    environment["PGDATABASE"] = unquote(parsed.path.lstrip("/"))
    if parsed.username:
        environment["PGUSER"] = unquote(parsed.username)
    if parsed.password is not None:
        environment["PGPASSWORD"] = unquote(parsed.password)
    query = parse_qs(parsed.query, keep_blank_values=False)
    unknown = set(query) - set(_ALLOWED_QUERY_ENV)
    if unknown:
        raise ValueError("unsupported_database_url_parameter")
    for key, env_name in _ALLOWED_QUERY_ENV.items():
        if key in query:
            if len(query[key]) != 1:
                raise ValueError("duplicate_database_url_parameter")
            environment[env_name] = query[key][0]
    return environment


def _database_identity(url: str) -> tuple[str, int, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("invalid_database_url")
    return parsed.hostname.lower(), parsed.port or 5432, unquote(parsed.path.lstrip("/"))


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], environment: dict[str, str]) -> None:
    executable = shutil.which(command[0])
    if executable is None:
        raise RuntimeError(f"required_postgres_tool_missing:{command[0]}")
    command[0] = executable
    completed = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        # Never print the command/environment or driver output; those may include connection details.
        raise RuntimeError(f"postgres_tool_failed:{Path(executable).name}:{completed.returncode}")


def backup() -> Path:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise ValueError("DATABASE_URL_required")
    environment = _connection_environment(url)
    directory = Path(os.environ.get("BACKUP_DIR", "backups")).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = directory / f"outreach-db-{timestamp}.dump"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".oma-backup-", suffix=".tmp", dir=directory)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _run(["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(temporary)], environment)
        if not temporary.exists() or temporary.stat().st_size == 0:
            raise RuntimeError("backup_output_empty")
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
        checksum_file = destination.with_suffix(destination.suffix + ".sha256")
        checksum_file.write_text(f"{_checksum(destination)}  {destination.name}\n", encoding="utf-8")
        os.chmod(checksum_file, 0o600)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def verify(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("backup_file_missing_or_empty")
    checksum_file = path.with_suffix(path.suffix + ".sha256")
    if not checksum_file.is_file():
        raise ValueError("backup_checksum_missing")
    expected = checksum_file.read_text(encoding="utf-8").split()[0]
    if not expected or _checksum(path) != expected:
        raise ValueError("backup_checksum_mismatch")
    _run(["pg_restore", "--list", str(path)], dict(os.environ))


def restore(path: Path) -> None:
    verify(path)
    source_url = os.environ.get("SOURCE_DATABASE_URL", "").strip()
    target_url = os.environ.get("RESTORE_DATABASE_URL", "").strip()
    if not source_url or not target_url:
        raise ValueError("SOURCE_DATABASE_URL_and_RESTORE_DATABASE_URL_required")
    if _database_identity(source_url) == _database_identity(target_url):
        raise ValueError("restore_target_must_differ_from_source_database")
    if os.environ.get("CONFIRM_RESTORE") != "YES":
        raise ValueError("set_CONFIRM_RESTORE_YES_for_explicit_restore")
    environment = _connection_environment(target_url)
    # No --clean: restore is intended for a newly created empty recovery database.
    _run(["pg_restore", "--exit-on-error", "--no-owner", "--no-privileges", "--dbname", environment["PGDATABASE"], str(path)], environment)


def main() -> int:
    parser = argparse.ArgumentParser(description="PostgreSQL backup and recovery helper")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("backup")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("backup_file", type=Path)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("backup_file", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "backup":
            path = backup()
            print(f"Backup created: {path} (SHA-256 sidecar written).")
        elif args.action == "verify":
            verify(args.backup_file)
            print("Backup checksum and PostgreSQL archive directory verified.")
        else:
            restore(args.backup_file)
            print("Restore command completed against the explicitly configured recovery database.")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Database recovery operation stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
