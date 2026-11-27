from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import account_routes
from app.main import app


class FakeConnection:
    def __init__(self, *, blocked: bool = False):
        self.blocked = blocked
        self.executed: list[tuple[str, tuple]] = []
        self.fetch_queries: list[tuple[str, tuple]] = []
        self.fetchval_queries: list[str] = []

    @asynccontextmanager
    async def transaction(self, **kwargs):
        yield

    async def fetchrow(self, query, *args):
        if "SELECT id,status,email FROM app_users" in query:
            return {"id": args[0], "status": "active", "email": "user@example.test"}
        raise AssertionError("unexpected fetchrow query")

    async def fetch(self, query, *args):
        self.fetch_queries.append((query, args))
        return []

    async def fetchval(self, query, *args):
        self.fetchval_queries.append(query)
        assert "transfer_workspace_ownership" not in query
        return self.blocked

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "UPDATE 1"


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


class FakeAccountAuthStore:
    async def authenticate_password(self, *, email, password):
        if email == "user@example.test" and password == "correct-password":
            return {"user_id": "00000000-0000-0000-0000-000000000001", "email": email}
        return None


async def _authenticated(request):
    return (FakeAccountAuthStore(), None, {"user_id": "00000000-0000-0000-0000-000000000001", "email": "user@example.test"})


def test_delete_account_revokes_sessions_pseudonymizes_identity_and_clears_cookies(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(account_routes, "_authenticated", _authenticated)
    monkeypatch.setattr(account_routes, "_check_csrf", lambda request, session: None)
    with TestClient(app) as client:
        app.state.db_pool = FakePool(conn)
        response = client.delete("/api/v1/account", json={"password": "correct-password"})
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert "deleted+00000000000000000000000000000001@accounts.invalid" in str(conn.executed)
    assert any("UPDATE auth_sessions SET revoked_at=now()" in sql for sql, _ in conn.executed)
    assert any("UPDATE workspace_memberships SET status='revoked'" in sql and "status<>'revoked'" in sql for sql, _ in conn.executed)
    assert any("deleted_at=now()" in sql for sql, _ in conn.executed)
    invitation_update = next(sql for sql, _ in conn.executed if "UPDATE workspace_invitations" in sql)
    assert "invited_by=$1 OR invited_email=$2" in invitation_update
    assert any("ORDER BY w.id FOR UPDATE OF w" in sql for sql, _ in conn.fetch_queries)
    assert any("UPDATE app_users" in sql and "status='deleted'" in sql for sql, _ in conn.executed)
    password_update = next(args for sql, args in conn.executed if "UPDATE app_users" in sql)
    assert password_update[2].startswith("scrypt$")
    assert "deleted$" not in password_update[2]
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any("__Host-oma_session=" in value and ("=;" in value or '=""' in value) for value in set_cookie_headers)
    assert any("__Host-oma_csrf=" in value and ("=;" in value or '=""' in value) for value in set_cookie_headers)
    assert "Cache-Control" in response.headers


def test_delete_account_refuses_to_orphan_workspace_with_any_non_revoked_member(monkeypatch):
    conn = FakeConnection(blocked=True)
    monkeypatch.setattr(account_routes, "_authenticated", _authenticated)
    monkeypatch.setattr(account_routes, "_check_csrf", lambda request, session: None)
    with TestClient(app) as client:
        app.state.db_pool = FakePool(conn)
        response = client.delete("/api/v1/account")
    assert response.status_code == 409
    assert response.json()["detail"] == "transfer_workspace_ownership_before_account_deletion"
    assert conn.executed == []
    ownership_guard = conn.fetchval_queries[0]
    assert "own.status<>'revoked'" in ownership_guard
    assert "other.status<>'revoked'" in ownership_guard


def test_delete_account_requires_csrf_before_database_access(monkeypatch):
    class NeverPool:
        @asynccontextmanager
        async def acquire(self):
            raise AssertionError("database must not be touched without CSRF")
            yield

    monkeypatch.setattr(account_routes, "_authenticated", _authenticated)

    def reject_csrf(request, session):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="csrf_rejected")

    monkeypatch.setattr(account_routes, "_check_csrf", reject_csrf)
    with TestClient(app) as client:
        app.state.db_pool = NeverPool()
        response = client.delete("/api/v1/account")
    assert response.status_code == 403


class FakeExportConnection:
    def __init__(self):
        self.fetch_queries: list[str] = []

    @asynccontextmanager
    async def transaction(self, **kwargs):
        assert kwargs == {"isolation": "repeatable_read", "readonly": True}
        yield

    async def fetchrow(self, query, *args):
        assert "FROM app_users" in query
        return {"id": args[0], "email": "user@example.test", "status": "active"}

    async def fetch(self, query, *args):
        self.fetch_queries.append(query)
        if "FROM workspaces w JOIN workspace_memberships" in query:
            return [{
                "workspace_id": "workspace-export-test",
                "workspace_name": "Example workspace",
                "workspace_created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "role": "owner",
                "membership_created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }]
        return []


def test_account_export_includes_workspace_names_and_domain_verification_records(monkeypatch):
    conn = FakeExportConnection()
    monkeypatch.setattr(account_routes, "_authenticated", _authenticated)
    with TestClient(app) as client:
        app.state.db_pool = FakePool(conn)
        response = client.get("/api/v1/account/export")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspaces"][0]["workspace_name"] == "Example workspace"
    assert payload["domains"] == []
    assert any("FROM workspace_domains" in query for query in conn.fetch_queries)
    whatsapp_account_query = next(
        query for query in conn.fetch_queries if "FROM workspace_whatsapp_accounts" in query
    )
    assert "waba_id AS business_account_id" in whatsapp_account_query
    assert "phone_number_id,business_account_id" not in whatsapp_account_query
    preferences_query = next(
        query for query in conn.fetch_queries if "FROM whatsapp_contact_preferences" in query
    )
    # Export only columns guaranteed by migrations 023/024; optional inbound fields
    # must not make the entire privacy export fail on a fresh database.
    assert "last_opt_out_message_id" in preferences_query
    assert "last_inbound_at" not in preferences_query
    assert "last_inbound_message_id" not in preferences_query
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "no-store, private"


def test_account_export_marks_workspace_scoped_collections_when_memberships_are_bounded(monkeypatch):
    conn = FakeExportConnection()

    async def fetch_many(query, *args):
        conn.fetch_queries.append(query)
        if "FROM workspaces w JOIN workspace_memberships" in query:
            return [
                {
                    "workspace_id": f"workspace-{index:03d}",
                    "workspace_name": f"Workspace {index}",
                    "workspace_created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    "role": "owner",
                    "membership_created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                }
                for index in range(101)
            ]
        return []

    conn.fetch = fetch_many
    monkeypatch.setattr(account_routes, "_authenticated", _authenticated)
    with TestClient(app) as client:
        app.state.db_pool = FakePool(conn)
        response = client.get("/api/v1/account/export")

    assert response.status_code == 200
    truncated = response.json()["limits"]["truncated_collections"]
    assert "workspaces" in truncated
    assert "workspace_scoped_collections" in truncated


def test_account_export_discloses_operational_collections_not_included(monkeypatch):
    conn = FakeExportConnection()
    monkeypatch.setattr(account_routes, "_authenticated", _authenticated)
    with TestClient(app) as client:
        app.state.db_pool = FakePool(conn)
        response = client.get("/api/v1/account/export")

    assert response.status_code == 200
    limits = response.json()["limits"]
    assert limits["not_included_collections"] == []
    assert "workspace_growth_schedules" in response.json()
    assert "workspace_jobs" in response.json()
    assert "followup_sequences" in response.json()
    assert "followup_steps" in response.json()
    assert "followup_enrollments" in response.json()
    assert "followup_delivery_resolutions" in response.json()
    assert "email_provider_events" in response.json()
    assert "whatsapp_conversation_notes" in response.json()
    assert "whatsapp_conversation_activity" in response.json()
    assert "whatsapp_inbox_saved_views" in response.json()
    assert "whatsapp_inbox_sla_policies" in response.json()
    assert "not a complete system backup" in limits["note"]


def test_account_export_queries_all_operational_workspace_histories(monkeypatch):
    conn = FakeExportConnection()
    monkeypatch.setattr(account_routes, "_authenticated", _authenticated)
    with TestClient(app) as client:
        app.state.db_pool = FakePool(conn)
        response = client.get("/api/v1/account/export")

    assert response.status_code == 200
    expected_tables = (
        "workspace_growth_schedules", "workspace_jobs", "outreach_followup_sequences",
        "outreach_followup_steps", "outreach_followup_enrollments",
        "outreach_followup_delivery_resolutions", "email_provider_events",
        "whatsapp_conversation_notes", "whatsapp_conversation_activity",
        "whatsapp_inbox_saved_views", "whatsapp_inbox_sla_policies",
    )
    for table in expected_tables:
        assert any(table in query for query in conn.fetch_queries), table
