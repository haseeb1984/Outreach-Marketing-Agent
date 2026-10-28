"""Fail-closed, machine-readable release preflight for production operators.

Run from the repository root:
    python -m backend.scripts.launch_preflight
or from backend/:
    python -m scripts.launch_preflight

This validates configuration and required operational artifacts. It does not claim
that a remote deployment, live provider, database migration, or restore drill succeeded.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlsplit


REQUIRED_RELEASE_MIGRATIONS = (
    "035_workspace_growth_schedules.sql",
    "036_growth_schedule_quota_status.sql",
    "037_whatsapp_outbound_template_persistence.sql",
    "038_whatsapp_outbound_queue_leases.sql",
)


def _https_origin(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and parsed.path in ("", "/") and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def _valid_key(value: str) -> bool:
    if not value.strip():
        return False
    raw = value.strip()
    try:
        decoded = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error):
        return False
    return len(decoded) == 32


def evaluate_config(env: Mapping[str, str], root: Path) -> dict:
    """Return named checks with explicit severity; never include secret values."""
    checks: list[dict[str, str]] = []

    def add(name: str, ok: bool, detail: str, severity: str = "error") -> None:
        checks.append({"name": name, "status": "pass" if ok else
                       ("warning" if severity == "warning" else "fail"), "detail": detail})

    dsn = env.get("DATABASE_URL", "").strip()
    dsn_ok = dsn.startswith(("postgres://", "postgresql://"))
    add("database_url", dsn_ok, "PostgreSQL DATABASE_URL configured" if dsn_ok
        else "DATABASE_URL must use postgres:// or postgresql://")

    secret = env.get("SECRET_KEY", "")
    secret_ok = len(secret.encode("utf-8")) >= 32
    add("session_secret", secret_ok, "session secret meets minimum length" if secret_ok
        else "SECRET_KEY must contain at least 32 UTF-8 bytes")

    encrypted_key = env.get("PROVIDER_CREDENTIAL_ENCRYPTION_KEY", "")
    key_ok = _valid_key(encrypted_key)
    add("provider_encryption_key", key_ok, "provider encryption key decodes to 32 bytes" if key_ok
        else "PROVIDER_CREDENTIAL_ENCRYPTION_KEY must be valid base64/base64url for exactly 32 bytes")

    public_url = env.get("PUBLIC_BASE_URL", "").strip()
    public_ok = _https_origin(public_url)
    add("public_base_url", public_ok, "canonical public URL is an HTTPS origin" if public_ok
        else "PUBLIC_BASE_URL must be an HTTPS origin without path, query, or fragment")

    origins = [v.strip() for v in env.get("FRONTEND_ORIGINS", "").split(",") if v.strip()]
    origins_ok = bool(origins) and all(_https_origin(v) for v in origins)
    add("frontend_origins", origins_ok, "all configured frontend origins are HTTPS origins" if origins_ok
        else "FRONTEND_ORIGINS must contain one or more comma-separated HTTPS origins")

    smtp_fields = ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL")
    smtp_present = [bool(env.get(k, "").strip()) for k in smtp_fields]
    smtp_ok = not any(smtp_present) or all(smtp_present)
    add("smtp_configuration", smtp_ok, "SMTP settings are either fully configured or fully absent" if smtp_ok
        else "SMTP configuration is partial; set all of SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL")

    paddle_env = env.get("PADDLE_ENVIRONMENT", "sandbox").strip().lower()
    live_checkout = env.get("PADDLE_LIVE_CHECKOUT_ENABLED", "false").strip().lower() == "true"
    paddle_ok = paddle_env in {"sandbox", "production"} and not (live_checkout and paddle_env != "production")
    add("paddle_mode", paddle_ok, "Paddle mode and live-checkout flag are consistent" if paddle_ok
        else "PADDLE_ENVIRONMENT must be sandbox/production; live checkout requires production mode")

    meta_fields = ("META_WHATSAPP_ACCESS_TOKEN", "META_WHATSAPP_APP_SECRET",
                   "META_WHATSAPP_WEBHOOK_VERIFY_TOKEN", "META_WHATSAPP_PHONE_NUMBER_ID",
                   "META_WHATSAPP_WABA_ID", "META_GRAPH_API_VERSION")
    meta_count = sum(bool(env.get(k, "").strip()) for k in meta_fields)
    meta_ok = meta_count in {0, len(meta_fields)}
    add("meta_whatsapp_configuration", meta_ok,
        "Meta global integration settings are complete or absent" if meta_ok
        else "Meta global integration settings are partial; configure all six values or none")

    graph_version = env.get("META_GRAPH_API_VERSION", "").strip()
    graph_ok = not graph_version or bool(re.fullmatch(r"v[0-9]{2,3}\.0", graph_version))
    add("meta_graph_version", graph_ok, "Meta Graph API version format is valid" if graph_ok
        else "META_GRAPH_API_VERSION must look like vXX.0")

    migrations = root / "backend" / "migrations"
    migration_files = sorted(migrations.glob("[0-9][0-9][0-9]_*.sql")) if migrations.is_dir() else []
    add("migration_artifacts", bool(migration_files),
        f"found {len(migration_files)} numbered SQL migration files" if migration_files
        else "numbered SQL migrations are missing")
    missing = [name for name in REQUIRED_RELEASE_MIGRATIONS if not (migrations / name).is_file()]
    add("required_release_migrations", not missing,
        "all required growth/WhatsApp release migrations are present" if not missing
        else "missing required migration files: " + ", ".join(missing))

    backup_script = root / "backend" / "scripts" / "database_backup.py"
    add("backup_tool", backup_script.is_file(), "database backup/verification tool exists" if backup_script.is_file()
        else "backend/scripts/database_backup.py is missing")

    worker_unit = root / "ops" / "systemd" / "outreach-growth-worker.service"
    add("growth_worker_supervision", worker_unit.is_file(), "growth worker systemd unit exists" if worker_unit.is_file()
        else "growth worker systemd unit is missing")

    worker_runbook = root / "docs" / "GROWTH_WORKER_HOST_RUNBOOK.md"
    add("growth_worker_runbook", worker_runbook.is_file(), "growth worker host runbook exists" if worker_runbook.is_file()
        else "docs/GROWTH_WORKER_HOST_RUNBOOK.md is missing")

    # Local files cannot prove these runtime facts.
    add("remote_deployment", False,
        "not verified by this local preflight; check the deployed commit and health endpoint", "warning")
    add("database_migration_execution", False,
        "migration files are present, but production database application is not verified", "warning")
    add("provider_acceptance", False,
        "live SMTP, Paddle, and WhatsApp acceptance must be verified independently", "warning")
    add("backup_restore_drill", False,
        "a real isolated restore rehearsal is required; file presence is not proof", "warning")

    failed = sum(c["status"] == "fail" for c in checks)
    warnings = sum(c["status"] == "warning" for c in checks)
    passed = sum(c["status"] == "pass" for c in checks)
    return {
        # Keep "ok" compatible with existing scripts: it means local checks passed.
        "ok": failed == 0,
        "launch_ready": failed == 0 and warnings == 0,
        "summary": {"passed": passed, "failed": failed, "warnings": warnings, "total": len(checks)},
        "checks": checks,
    }


def exit_code(result: Mapping[str, object], require_launch_ready: bool = False) -> int:
    """Map preflight results to a process status without weakening legacy behavior."""
    if not result.get("ok", False):
        return 1
    if require_launch_ready and not result.get("launch_ready", False):
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate release configuration and launch gates.")
    parser.add_argument("--require-launch-ready", action="store_true",
                        help="exit non-zero while any remote/runtime acceptance gate remains unverified")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    result = evaluate_config(os.environ, root)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return exit_code(result, require_launch_ready=args.require_launch_ready)


if __name__ == "__main__":
    raise SystemExit(main())
