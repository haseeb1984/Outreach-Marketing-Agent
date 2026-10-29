from __future__ import annotations

import base64
import json
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
    (root / "ops/systemd/outreach-growth-scheduler.service").write_text("# test")
    (root / "ops/systemd/outreach-whatsapp-dispatch-worker.service").write_text("# test")
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


def test_preflight_accepts_paddle_configuration_absent_when_checkout_is_disabled(tmp_path: Path):
    result = evaluate_config(_env(), tmp_path)
    assert _statuses(result)["paddle_credentials_and_catalog"] == "pass"


@pytest.mark.parametrize("configured", [
    {"PADDLE_API_KEY": "pdl_sandbox_key"},
    {"PADDLE_WEBHOOK_SECRET": "webhook-secret"},
    {"PADDLE_PLANS_JSON": '{"starter":{"price_id":"pri_starter","entitlements":{}}}'},
])
def test_preflight_rejects_partial_paddle_configuration(tmp_path: Path, configured: dict[str, str]):
    env = _env()
    env.update(configured)
    result = evaluate_config(env, tmp_path)
    assert result["ok"] is False
    assert _statuses(result)["paddle_credentials_and_catalog"] == "fail"


def test_preflight_requires_complete_paddle_setup_for_live_checkout(tmp_path: Path):
    env = _env()
    env.update({
        "PADDLE_ENVIRONMENT": "production",
        "PADDLE_LIVE_CHECKOUT_ENABLED": "true",
    })
    result = evaluate_config(env, tmp_path)
    assert result["ok"] is False
    assert _statuses(result)["paddle_credentials_and_catalog"] == "fail"


def test_preflight_accepts_complete_paddle_setup_for_live_checkout(tmp_path: Path):
    env = _env()
    env.update({
        "PADDLE_ENVIRONMENT": "production",
        "PADDLE_LIVE_CHECKOUT_ENABLED": "true",
        "PADDLE_API_KEY": "pdl_live_key",
        "PADDLE_WEBHOOK_SECRET": "webhook-secret",
        "PADDLE_PLANS_JSON": "{\"starter\":{\"price_id\":\"pri_starter\",\"entitlements\":{\"ai_draft_generations\":{\"enabled\":true,\"monthly_limit\":250},\"email_sends\":{\"enabled\":true,\"monthly_limit\":1000},\"website_audits\":{\"enabled\":true,\"monthly_limit\":25},\"whatsapp_sends\":{\"enabled\":false,\"monthly_limit\":0}}}}",
    })
    result = evaluate_config(env, tmp_path)
    assert _statuses(result)["paddle_credentials_and_catalog"] == "pass"


@pytest.mark.parametrize("catalog", [
    "not-json",
    "[]",
    '{"starter":{"price_id":"bad_id","entitlements":{}}}',
    '{"starter":{"price_id":"pri_same","entitlements":{}},"growth":{"price_id":"pri_same","entitlements":{}}}',
    '{"Starter":{"price_id":"pri_starter","entitlements":{}}}',
    '{"starter":{"price_id":"pri_starter"}}',
])
def test_preflight_rejects_invalid_paddle_plan_catalog_shape(tmp_path: Path, catalog: str):
    env = _env()
    env.update({
        "PADDLE_API_KEY": "pdl_sandbox_key",
        "PADDLE_WEBHOOK_SECRET": "webhook-secret",
        "PADDLE_PLANS_JSON": catalog,
    })
    result = evaluate_config(env, tmp_path)
    assert _statuses(result)["paddle_credentials_and_catalog"] == "pass"
    assert _statuses(result)["paddle_plan_catalog_shape"] == "fail"
    assert result["ok"] is False
    assert catalog not in str(result)


def test_preflight_accepts_valid_unique_sandbox_plan_catalog(tmp_path: Path):
    env = _env()
    env.update({
        "PADDLE_API_KEY": "pdl_sandbox_key",
        "PADDLE_WEBHOOK_SECRET": "webhook-secret",
        "PADDLE_PLANS_JSON": "{\"starter\":{\"price_id\":\"pri_starter\",\"entitlements\":{\"ai_draft_generations\":{\"enabled\":true,\"monthly_limit\":250},\"email_sends\":{\"enabled\":true,\"monthly_limit\":1000},\"website_audits\":{\"enabled\":true,\"monthly_limit\":25},\"whatsapp_sends\":{\"enabled\":false,\"monthly_limit\":0}}},\"growth\":{\"price_id\":\"pri_growth\",\"entitlements\":{\"ai_draft_generations\":{\"enabled\":true,\"monthly_limit\":1000},\"email_sends\":{\"enabled\":true,\"monthly_limit\":5000},\"website_audits\":{\"enabled\":true,\"monthly_limit\":100},\"whatsapp_sends\":{\"enabled\":true,\"monthly_limit\":1000}}},\"agency\":{\"price_id\":\"pri_agency\",\"entitlements\":{\"ai_draft_generations\":{\"enabled\":true,\"monthly_limit\":5000},\"email_sends\":{\"enabled\":true,\"monthly_limit\":25000},\"website_audits\":{\"enabled\":true,\"monthly_limit\":500},\"whatsapp_sends\":{\"enabled\":true,\"monthly_limit\":10000}}}}",
    })
    result = evaluate_config(env, tmp_path)
    assert _statuses(result)["paddle_credentials_and_catalog"] == "pass"
    assert _statuses(result)["paddle_plan_catalog_shape"] == "pass"


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


def _complete_policy(drafts=250, emails=1000, audits=25, whatsapp=0, whatsapp_enabled=False):
    return {
        "ai_draft_generations": {"enabled": True, "monthly_limit": drafts},
        "email_sends": {"enabled": True, "monthly_limit": emails},
        "website_audits": {"enabled": True, "monthly_limit": audits},
        "whatsapp_sends": {"enabled": whatsapp_enabled, "monthly_limit": whatsapp},
    }


def test_live_checkout_rejects_empty_entitlements_even_with_valid_price_ids(tmp_path: Path):
    env = _env()
    env.update({
        "PADDLE_ENVIRONMENT": "production",
        "PADDLE_LIVE_CHECKOUT_ENABLED": "true",
        "PADDLE_API_KEY": "pdl_live_key",
        "PADDLE_WEBHOOK_SECRET": "webhook-secret",
        "PADDLE_PLANS_JSON": json.dumps({
            "starter": {"price_id": "pri_starter", "entitlements": {}},
            "growth": {"price_id": "pri_growth", "entitlements": {}},
        }),
    })
    result = evaluate_config(env, tmp_path)
    assert _statuses(result)["paddle_plan_catalog_shape"] == "pass"
    assert _statuses(result)["paddle_live_entitlements"] == "fail"
    assert result["ok"] is False


def test_live_checkout_requires_entitlements_for_every_plan(tmp_path: Path):
    env = _env()
    env.update({
        "PADDLE_ENVIRONMENT": "production",
        "PADDLE_LIVE_CHECKOUT_ENABLED": "true",
        "PADDLE_API_KEY": "pdl_live_key",
        "PADDLE_WEBHOOK_SECRET": "webhook-secret",
        "PADDLE_PLANS_JSON": json.dumps({
            "starter": {"price_id": "pri_starter", "entitlements": _complete_policy()},
            "growth": {"price_id": "pri_growth", "entitlements": {}},
        }),
    })
    result = evaluate_config(env, tmp_path)
    assert _statuses(result)["paddle_live_entitlements"] == "fail"


def test_live_checkout_accepts_explicit_entitlements_for_every_plan(tmp_path: Path):
    env = _env()
    env.update({
        "PADDLE_ENVIRONMENT": "production",
        "PADDLE_LIVE_CHECKOUT_ENABLED": "true",
        "PADDLE_API_KEY": "pdl_live_key",
        "PADDLE_WEBHOOK_SECRET": "webhook-secret",
        "PADDLE_PLANS_JSON": json.dumps({
            "starter": {"price_id": "pri_starter", "entitlements": _complete_policy()},
            "growth": {"price_id": "pri_growth", "entitlements": _complete_policy(1000, 5000, 100, 1000, True)},
        }),
    })
    result = evaluate_config(env, tmp_path)
    assert _statuses(result)["paddle_live_entitlements"] == "pass"


def test_preflight_rejects_catalog_missing_a_quota_controlled_feature(tmp_path: Path):
    env = _env()
    env.update({
        "PADDLE_API_KEY": "pdl_sandbox_key",
        "PADDLE_WEBHOOK_SECRET": "webhook-secret",
        "PADDLE_PLANS_JSON": json.dumps({
            "starter": {"price_id": "pri_starter", "entitlements": {
                "email_sends": {"enabled": True, "monthly_limit": 100}
            }}
        }),
    })
    result = evaluate_config(env, tmp_path)
    assert _statuses(result)["paddle_live_entitlements"] == "fail"
    assert result["ok"] is False


def test_preflight_rejects_boolean_quota_and_malformed_policy(tmp_path: Path):
    env = _env()
    policy = _complete_policy()
    policy["email_sends"]["monthly_limit"] = True
    env.update({
        "PADDLE_API_KEY": "pdl_sandbox_key",
        "PADDLE_WEBHOOK_SECRET": "webhook-secret",
        "PADDLE_PLANS_JSON": json.dumps({
            "starter": {"price_id": "pri_starter", "entitlements": policy}
        }),
    })
    result = evaluate_config(env, tmp_path)
    assert _statuses(result)["paddle_live_entitlements"] == "fail"
