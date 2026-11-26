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
    "039_website_audit_job_idempotency.sql",
    "040_email_provider_feedback.sql",
    "041_campaign_delivery_scheduling.sql",
    "042_whatsapp_template_components.sql",
    "043_whatsapp_inbound_media_storage.sql",
    "044_whatsapp_inbox_collaboration.sql",
    "045_whatsapp_conversation_activity.sql",
    "046_whatsapp_inbox_saved_views.sql",
    "047_whatsapp_inbox_sla_policies.sql",
    "048_whatsapp_inbox_sla_pause_resume.sql",
    "049_campaign_followup_sequences.sql",
    "050_followup_delivery_resolutions.sql",
    "051_billing_transactions.sql",
    "052_billing_event_fingerprints.sql",
    "053_billing_transaction_event_fingerprints.sql",
    "054_whatsapp_tenant_integrity.sql",
    "055_whatsapp_webhook_retry_tracking.sql",
    "056_billing_transaction_past_due.sql",
    "057_core_outreach_tenant_integrity.sql",
    "058_draft_request_idempotency.sql",
    "059_workspace_display_name.sql",
    "060_account_deletion_lifecycle.sql",
    "061_workspace_delivery_cascade_consistency.sql",
    "062_followup_resolution_tenant_cleanup.sql",
    "063_platform_billing_price_history.sql",
    "064_daily_prospect_research_quota.sql",
    "065_website_content_briefs.sql",
    "066_website_content_articles.sql",
    "067_wordpress_content_delivery.sql",
    "068_project_scoped_wordpress_connections.sql",
    "069_workspace_research_history.sql",
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
    "email_provider_events", "whatsapp_conversation_notes",
    "whatsapp_conversation_activity", "whatsapp_inbox_saved_views",
    "whatsapp_inbox_sla_policies", "outreach_followup_sequences",
    "outreach_followup_steps", "outreach_followup_enrollments",
    "outreach_followup_delivery_resolutions", "billing_transaction_events",
    "billing_transactions",
    "platform_billing_plan_price_history",
    "daily_feature_usage_reservations",
    "website_content_briefs",
    "workspace_wordpress_connections",
    "workspace_research_runs",
)

REQUIRED_CONSTRAINTS = (
    "whatsapp_conversations_account_workspace_fk",
    "whatsapp_conversations_prospect_workspace_fk",
    "whatsapp_inbound_messages_conversation_workspace_fk",
    "whatsapp_conversation_notes_workspace_fk",
    "whatsapp_conversation_activity_workspace_fk",
    "whatsapp_delivery_status_events_account_workspace_fk",
    "outreach_drafts_campaign_workspace_fk",
    "outreach_drafts_prospect_workspace_fk",
    "outreach_deliveries_draft_workspace_fk",
    "outreach_deliveries_email_account_workspace_fk",
)

REQUIRED_INDEXES = (
    "workspace_whatsapp_accounts_id_workspace_uidx",
    "crm_prospects_id_workspace_uidx",
    "whatsapp_conversations_id_workspace_uidx",
    "outreach_campaigns_id_workspace_uidx",
    "outreach_drafts_id_workspace_uidx",
    "workspace_email_accounts_id_workspace_uidx",
    "platform_billing_plan_price_history_slug_idx",
    "idx_daily_feature_usage_workspace_day",
    "website_content_briefs_workspace_status_idx",
    "idx_content_briefs_cms_status",
    "workspace_wordpress_connections_workspace_fallback_uidx",
    "workspace_wordpress_connections_project_uidx",
    "workspace_wordpress_connections_project_status_idx",
    "workspace_research_runs_history_idx",
)

REQUIRED_COLUMNS = (
    ("workspace_growth_schedules", "last_error_code"),
    ("crm_prospects", "contact_phone_e164"),
    ("whatsapp_outbound_deliveries", "template_name"),
    ("whatsapp_outbound_deliveries", "language_code"),
    ("whatsapp_outbound_deliveries", "lease_token"),
    ("whatsapp_outbound_deliveries", "lease_expires_at"),
    ("website_audit_reports", "job_id"),
    ("outreach_deliveries", "provider_status"),
    ("outreach_deliveries", "scheduled_at"),
    ("outreach_contact_controls", "email_suppression_reason"),
    ("whatsapp_message_templates", "components"),
    ("whatsapp_outbound_deliveries", "template_parameters"),
    ("whatsapp_inbound_messages", "media_ciphertext"),
    ("whatsapp_conversations", "inbox_status"),
    ("whatsapp_conversations", "sla_paused_at"),
    ("whatsapp_conversation_activity", "event_type"),
    ("meta_whatsapp_webhook_events", "attempts"),
    ("billing_provider_events", "event_fingerprint"),
    ("billing_transaction_events", "event_fingerprint"),
    ("billing_transactions", "status"),
    ("website_content_briefs", "article_title"),
    ("website_content_briefs", "article_body"),
    ("website_content_briefs", "article_status"),
    ("website_content_briefs", "cms_connection_id"),
    ("website_content_briefs", "cms_status"),
    ("workspace_wordpress_connections", "project_id"),
    ("workspace_research_runs", "research_type"),
    ("workspace_research_runs", "parameters"),
    ("workspace_research_runs", "results"),
    ("daily_feature_usage_reservations", "usage_date"),
)


def evaluate_schema_state(
    local_migrations: Iterable[str],
    applied_migrations: Iterable[str],
    present_tables: Iterable[str],
    present_columns: Iterable[tuple[str, str]],
    present_constraints: Iterable[str] = REQUIRED_CONSTRAINTS,
    present_indexes: Iterable[str] = REQUIRED_INDEXES,
) -> dict:
    """Pure evaluator, separated from DB I/O for deterministic unit tests."""
    local_migration_names = list(local_migrations)
    local = set(local_migration_names)
    applied = set(applied_migrations)
    tables = set(present_tables)
    columns = set(present_columns)
    constraints = set(present_constraints)
    indexes = set(present_indexes)

    missing_local = [name for name in REQUIRED_MIGRATIONS if name not in local]
    missing_applied = [name for name in local_migration_names if name not in applied]
    missing_tables = [name for name in REQUIRED_TABLES if name not in tables]
    missing_columns = [f"{table}.{column}" for table, column in REQUIRED_COLUMNS
                       if (table, column) not in columns]
    missing_constraints = [name for name in REQUIRED_CONSTRAINTS if name not in constraints]
    missing_indexes = [name for name in REQUIRED_INDEXES if name not in indexes]

    checks = [
        {"name": "migration_files", "status": "pass" if not missing_local else "fail",
         "missing": missing_local},
        {"name": "migration_ledger", "status": "pass" if not missing_applied else "fail",
         "missing": missing_applied},
        {"name": "required_tables", "status": "pass" if not missing_tables else "fail",
         "missing": missing_tables},
        {"name": "required_columns", "status": "pass" if not missing_columns else "fail",
         "missing": missing_columns},
        {"name": "tenant_integrity_constraints",
         "status": "pass" if not missing_constraints else "fail",
         "missing": missing_constraints},
        {"name": "tenant_integrity_indexes",
         "status": "pass" if not missing_indexes else "fail",
         "missing": missing_indexes},
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
        local_migrations = sorted(path.name for path in migrations_dir.glob("[0-9][0-9][0-9]_*.sql"))

        ledger_exists = await connection.fetchval(
            "SELECT to_regclass('public.schema_migrations') IS NOT NULL"
        )
        applied: list[str] = []
        if ledger_exists:
            rows = await connection.fetch(
                "SELECT version FROM schema_migrations WHERE version = ANY($1::text[])",
                local_migrations,
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
                   SELECT * FROM unnest($1::text[], $2::text[])
                 )""",
            [table for table, _ in REQUIRED_COLUMNS],
            [column for _, column in REQUIRED_COLUMNS],
        )
        present_columns = [(row["table_name"], row["column_name"]) for row in column_rows]
        constraint_rows = await connection.fetch(
            """SELECT conname FROM pg_constraint
               WHERE connamespace = 'public'::regnamespace
                 AND convalidated = TRUE
                 AND conname = ANY($1::text[])""",
            list(REQUIRED_CONSTRAINTS),
        )
        present_constraints = [row["conname"] for row in constraint_rows]
        index_rows = await connection.fetch(
            """SELECT indexname FROM pg_indexes
               WHERE schemaname = 'public' AND indexname = ANY($1::text[])""",
            list(REQUIRED_INDEXES),
        )
        present_indexes = [row["indexname"] for row in index_rows]
        return evaluate_schema_state(
            local_migrations, applied, present_tables, present_columns,
            present_constraints, present_indexes,
        )
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
