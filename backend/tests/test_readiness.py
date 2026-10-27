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
    assert response.json() == {"status": "ready"}
    for migration in (
        "015_workspace_projects.sql",
        "016_workspace_invitations.sql",
        "017_workspace_settings.sql",
        "018_workspace_email_accounts.sql",
        "019_website_audit_reports.sql",
        "034_workspace_delivery_cascade_cleanup.sql",
        "035_workspace_growth_schedules.sql",
    ):
        assert migration in connection.schema_query
    for table in (
        "workspace_projects",
        "workspace_invitations",
        "workspace_email_accounts",
        "website_audit_reports",
        "workspace_growth_schedules",
    ):
        assert f"public.{table}" in connection.schema_query


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
