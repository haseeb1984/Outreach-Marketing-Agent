from __future__ import annotations

import base64
from pathlib import Path

import pytest

from scripts.launch_preflight import REQUIRED_RELEASE_MIGRATIONS, evaluate_config, exit_code


def _env() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql://app:secret@localhost/app",
        "SECRET_KEY": "x" * 40,
        "PROVIDER_CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"k" * 32).decode(),
        "PUBLIC_BASE_URL": "https://example.com",
        "FRONTEND_ORIGINS": "https://example.com,https://app.example.com",
        "PADDLE_ENVIRONMENT": "sandbox",
        "PADDLE_LIVE_CHECKOUT_ENABLED": "false",
    }


def _statuses(result):
    return {item["name"]: item["status"] for item in result["checks"]}


def _release_root(root: Path) -> None:
    migrations = root / "backend/migrations"
    migrations.mkdir(parents=True)
    for name in ("001_test.sql", *REQUIRED_RELEASE_MIGRATIONS):
        (migrations / name).write_text("-- test migration")
    (root / "backend/scripts").mkdir(parents=True)
    (root / "backend/scripts/database_backup.py").write_text("# test")
    (root / "ops/systemd").mkdir(parents=True)
    (root / "ops/systemd/outreach-growth-worker.service").write_text("# test")
    (root / "docs").mkdir()
    (root / "docs/GROWTH_WORKER_HOST_RUNBOOK.md").write_text("# test")


def test_preflight_passes_valid_base_config_and_reports_runtime_gates(tmp_path: Path):
    _release_root(tmp_path)
    result = evaluate_config(_env(), tmp_path)
    assert result["ok"] is True
    assert result["launch_ready"] is False
    status = _statuses(result)
    assert status["database_url"] == "pass"
    assert status["provider_encryption_key"] == "pass"
    assert status["required_release_migrations"] == "pass"
    assert status["remote_deployment"] == "warning"
    assert status["database_migration_execution"] == "warning"
    assert result["summary"]["total"] >= 15


def test_legacy_exit_code_stays_green_for_valid_local_configuration(tmp_path: Path):
    _release_root(tmp_path)
    assert exit_code(evaluate_config(_env(), tmp_path)) == 0


def test_strict_launch_gate_fails_until_runtime_acceptance_is_verified(tmp_path: Path):
    _release_root(tmp_path)
    assert exit_code(evaluate_config(_env(), tmp_path), require_launch_ready=True) == 2


def test_preflight_fails_weak_session_secret_without_echoing_values(tmp_path: Path):
    env = _env()
    env["SECRET_KEY"] = "tiny-secret"
    result = evaluate_config(env, tmp_path)
    assert result["ok"] is False
    assert _statuses(result)["session_secret"] == "fail"
    assert exit_code(result, require_launch_ready=True) == 1
    assert "tiny-secret" not in str(result)


def test_preflight_rejects_invalid_encryption_key(tmp_path: Path):
    env = _env()
    env["PROVIDER_CREDENTIAL_ENCRYPTION_KEY"] = "not-a-key"
    assert _statuses(evaluate_config(env, tmp_path))["provider_encryption_key"] == "fail"


def test_preflight_rejects_non_https_or_path_frontend_origins(tmp_path: Path):
    env = _env()
    env["FRONTEND_ORIGINS"] = "http://example.com,https://example.com/path"
    assert _statuses(evaluate_config(env, tmp_path))["frontend_origins"] == "fail"


def test_preflight_flags_partial_smtp_configuration(tmp_path: Path):
    env = _env()
    env["SMTP_HOST"] = "smtp.example.com"
    assert _statuses(evaluate_config(env, tmp_path))["smtp_configuration"] == "fail"


def test_preflight_rejects_inconsistent_paddle_live_mode(tmp_path: Path):
    env = _env()
    env["PADDLE_LIVE_CHECKOUT_ENABLED"] = "true"
    assert _statuses(evaluate_config(env, tmp_path))["paddle_mode"] == "fail"


def test_preflight_flags_partial_meta_configuration(tmp_path: Path):
    env = _env()
    env["META_WHATSAPP_ACCESS_TOKEN"] = "configured"
    assert _statuses(evaluate_config(env, tmp_path))["meta_whatsapp_configuration"] == "fail"


def test_preflight_accepts_valid_meta_graph_version(tmp_path: Path):
    env = _env()
    env["META_GRAPH_API_VERSION"] = "v23.0"
    assert _statuses(evaluate_config(env, tmp_path))["meta_graph_version"] == "pass"


def test_preflight_rejects_malformed_meta_graph_version(tmp_path: Path):
    env = _env()
    env["META_GRAPH_API_VERSION"] = "23"
    assert _statuses(evaluate_config(env, tmp_path))["meta_graph_version"] == "fail"


def test_preflight_flags_missing_required_operational_artifacts(tmp_path: Path):
    status = _statuses(evaluate_config(_env(), tmp_path))
    assert status["migration_artifacts"] == "fail"
    assert status["required_release_migrations"] == "fail"
    assert status["backup_tool"] == "fail"
    assert status["growth_worker_supervision"] == "fail"
    assert status["growth_worker_runbook"] == "fail"


@pytest.mark.parametrize("migration", REQUIRED_RELEASE_MIGRATIONS)
def test_preflight_fails_when_any_critical_release_migration_is_missing(tmp_path: Path, migration: str):
    _release_root(tmp_path)
    (tmp_path / "backend/migrations" / migration).unlink()
    result = evaluate_config(_env(), tmp_path)
    assert result["ok"] is False
    assert _statuses(result)["required_release_migrations"] == "fail"
    missing_check = next(c for c in result["checks"] if c["name"] == "required_release_migrations")
    assert migration in missing_check["detail"]


def test_preflight_uses_safe_json_statuses_for_remote_gates(tmp_path: Path):
    result = evaluate_config(_env(), tmp_path)
    assert all(item["status"] in {"pass", "fail", "warning"} for item in result["checks"])
    assert "tiny-secret" not in str(result)
    assert "postgresql://app:secret@localhost/app" not in str(result)
