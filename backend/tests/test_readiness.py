from fastapi.testclient import TestClient

from app.main import app


def test_liveness_does_not_claim_database_readiness():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_readiness_fails_closed_when_database_is_not_configured():
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "not_ready",
            "reason": "database_not_configured",
        }



class _FakeConnection:
    def __init__(self, schema_ready=True):
        self.schema_ready = schema_ready
        self.schema_query = ""

    async def fetchval(self, query, *args):
        if query.strip() == "SELECT 1":
            return 1
        self.schema_query = query
        return self.schema_ready


class _AcquireContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _AcquireContext(self.connection)

    async def close(self):
        return None


def test_readiness_checks_all_migrations_and_phase_one_tables():
    connection = _FakeConnection(schema_ready=True)
    with TestClient(app) as client:
        app.state.db_pool = _FakePool(connection)
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
    for migration in (
        "015_workspace_projects.sql",
        "016_workspace_invitations.sql",
        "017_workspace_settings.sql",
        "018_workspace_email_accounts.sql",
        "019_website_audit_reports.sql",
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
    ):
        assert migration in connection.schema_query
    for table in (
        "workspace_projects",
        "workspace_invitations",
        "workspace_email_accounts",
        "website_audit_reports",
        "workspace_growth_schedules",
        "whatsapp_outbound_deliveries",
    ):
        assert f"public.{table}" in connection.schema_query
    for column in (
        "template_name", "language_code", "lease_token", "lease_expires_at",
        "job_id", "components", "template_parameters", "sla_paused_at",
        "event_type", "attempts", "event_fingerprint", "status",
    ):
        assert f"column_name='{column}'" in connection.schema_query
    for constraint in (
        "whatsapp_conversations_account_workspace_fk",
        "whatsapp_conversations_prospect_workspace_fk",
        "whatsapp_inbound_messages_conversation_workspace_fk",
        "whatsapp_conversation_notes_workspace_fk",
        "whatsapp_conversation_activity_workspace_fk",
        "whatsapp_delivery_status_events_account_workspace_fk",
    ):
        assert constraint in connection.schema_query
    for index in (
        "workspace_whatsapp_accounts_id_workspace_uidx",
        "crm_prospects_id_workspace_uidx",
        "whatsapp_conversations_id_workspace_uidx",
    ):
        assert index in connection.schema_query
    assert ")) = 71" in connection.schema_query


def test_readiness_rejects_incomplete_migration_chain():
    connection = _FakeConnection(schema_ready=False)
    with TestClient(app) as client:
        app.state.db_pool = _FakePool(connection)
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "reason": "database_schema_not_migrated",
    }
