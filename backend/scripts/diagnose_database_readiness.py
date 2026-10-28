"""Read-only diagnostics for the database schema readiness gate.

Run from backend/ with DATABASE_URL configured:
    python -m scripts.diagnose_database_readiness

This script never runs migrations or modifies database state. It prints JSON without
including the connection string or database error text.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Iterable

import asyncpg


REQUIRED_MIGRATIONS = (
    "001_workspace_domain_verification.sql",
    "002_workspace_jobs.sql",
    "003_authentication_foundation.sql",
    "004_auth_rate_limits.sql",
    "005_session_csrf_tokens.sql",
    "006_password_reset_tokens.sql",
    "007_crm_prospects.sql",
    "008_campaigns_and_approval_queue.sql",
    "009_contact_controls.sql",
    "010_outbound_delivery_queue.sql",
    "011_conversation_webhook_inbox.sql",
    "012_delivery_outcome_uncertainty.sql",
    "013_subscription_entitlements_and_usage.sql",
    "014_billing_provider_event_ledger.sql",
    "015_workspace_projects.sql",
    "016_workspace_invitations.sql",
    "017_workspace_settings.sql",
    "018_workspace_email_accounts.sql",
    "019_website_audit_reports.sql",
    "020_meta_whatsapp_webhook_inbox.sql",
    "021_workspace_whatsapp_accounts.sql",
    "022_prospect_whatsapp_phone.sql",
    "023_whatsapp_conversations_and_status.sql",
    "024_whatsapp_contact_preferences.sql",
    "025_whatsapp_status_event_dedup.sql",
    "026_whatsapp_template_and_window_policy.sql",
    "027_platform_billing_admin.sql",
    "028_platform_admin_audit.sql",
    "029_unique_platform_plan_price_ids.sql",
    "030_subscription_plan_slug.sql",
    "031_whatsapp_outbound_queue.sql",
    "032_whatsapp_consent_account_scope.sql",
    "033_draft_edit_audit_event.sql",
    "034_workspace_delivery_cascade_cleanup.sql",
    "035_workspace_growth_schedules.sql",
    "036_growth_schedule_quota_status.sql",
    "037_whatsapp_outbound_template_persistence.sql",
    "038_whatsapp_outbound_queue_leases.sql",
)

REQUIRED_TABLES = (
    "workspace_domains", "workspace_projects", "workspace_invitations",
    "workspace_email_accounts", "website_audit_reports", "domain_verification_challenges",
    "workspace_jobs", "workspace_growth_schedules", "app_users", "workspace_memberships",
    "auth_sessions", "security_audit_events", "auth_rate_limit_buckets", "crm_prospects",
    "outreach_campaigns", "outreach_drafts", "outreach_draft_events", "outreach_contact_controls",
    "outreach_deliveries", "outreach_conversation_messages", "workspace_subscriptions",
    "feature_usage_reservations", "billing_provider_events", "schema_migrations",
    "meta_whatsapp_webhook_events", "workspace_whatsapp_accounts", "whatsapp_conversations",
    "whatsapp_inbound_messages", "whatsapp_delivery_status_events", "whatsapp_contact_preferences",
    "whatsapp_message_templates", "whatsapp_outbound_deliveries",
)

REQUIRED_COLUMNS = (
    ("workspace_growth_schedules", "last_error_code"),
    ("crm_prospects", "contact_phone_e164"),
    ("whatsapp_outbound_deliveries", "template_name"),
    ("whatsapp_outbound_deliveries", "language_code"),
    ("whatsapp_outbound_deliveries", "lease_token"),
    ("whatsapp_outbound_deliveries", "lease_expires_at"),
)


def evaluate_schema_state(
    local_migrations: Iterable[str],
    applied_migrations: Iterable[str],
    present_tables: Iterable[str],
    present_columns: Iterable[tuple[str, str]],
) -> dict:
    """Pure evaluator, separated from DB I/O for deterministic unit tests."""
    local = set(local_migrations)
    applied = set(applied_migrations)
    tables = set(present_tables)
    columns = set(present_columns)

    missing_local = [name for name in REQUIRED_MIGRATIONS if name not in local]
    missing_applied = [name for name in REQUIRED_MIGRATIONS if name not in applied]
    missing_tables = [name for name in REQUIRED_TABLES if name not in tables]
    missing_columns = [f"{table}.{column}" for table, column in REQUIRED_COLUMNS
                       if (table, column) not in columns]

    checks = [
        {"name": "migration_files", "status": "pass" if not missing_local else "fail",
         "missing": missing_local},
        {"name": "migration_ledger", "status": "pass" if not missing_applied else "fail",
         "missing": missing_applied},
        {"name": "required_tables", "status": "pass" if not missing_tables else "fail",
         "missing": missing_tables},
        {"name": "required_columns", "status": "pass" if not missing_columns else "fail",
         "missing": missing_columns},
    ]
    failed = sum(check["status"] == "fail" for check in checks)
    return {
        "status": "ready" if failed == 0 else "not_ready",
        "ok": failed == 0,
        "summary": {"passed": len(checks) - failed, "failed": failed, "total": len(checks)},
        "checks": checks,
    }


async def inspect_database(database_url: str, root: Path) -> dict:
    """Inspect the live schema using SELECT-only queries."""
    connection = await asyncpg.connect(database_url, timeout=5, command_timeout=10)
    try:
        migrations_dir = root / "migrations"
        local_migrations = [path.name for path in migrations_dir.glob("[0-9][0-9][0-9]_*.sql")]

        ledger_exists = await connection.fetchval(
            "SELECT to_regclass('public.schema_migrations') IS NOT NULL"
        )
        applied: list[str] = []
        if ledger_exists:
            rows = await connection.fetch(
                "SELECT version FROM schema_migrations WHERE version = ANY($1::text[])",
                list(REQUIRED_MIGRATIONS),
            )
            applied = [row["version"] for row in rows]

        table_rows = await connection.fetch(
            """SELECT table_name, to_regclass('public.' || table_name) IS NOT NULL AS present
               FROM unnest($1::text[]) AS table_name""",
            list(REQUIRED_TABLES),
        )
        present_tables = [row["table_name"] for row in table_rows if row["present"]]

        column_rows = await connection.fetch(
            """SELECT table_name, column_name
               FROM information_schema.columns
               WHERE table_schema='public'
                 AND (table_name, column_name) IN (
                   ('workspace_growth_schedules','last_error_code'),
                   ('crm_prospects','contact_phone_e164'),
                   ('whatsapp_outbound_deliveries','template_name'),
                   ('whatsapp_outbound_deliveries','language_code'),
                   ('whatsapp_outbound_deliveries','lease_token'),
                   ('whatsapp_outbound_deliveries','lease_expires_at')
                 )"""
        )
        present_columns = [(row["table_name"], row["column_name"]) for row in column_rows]
        return evaluate_schema_state(local_migrations, applied, present_tables, present_columns)
    finally:
        await connection.close()


async def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print(json.dumps({"status": "error", "ok": False,
                          "error": "DATABASE_URL is not configured"}, separators=(",", ":")))
        return 2

    root = Path(__file__).resolve().parents[1]
    try:
        result = await inspect_database(database_url, root)
    except Exception as exc:
        # Do not print exception text: database drivers can include connection details.
        print(json.dumps({"status": "error", "ok": False,
                          "error": "database_inspection_failed",
                          "error_type": type(exc).__name__}, separators=(",", ":")))
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
