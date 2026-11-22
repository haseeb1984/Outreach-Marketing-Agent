"""HTTP-level tenant role and platform-owner authorization acceptance tests."""
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from app.api import platform_admin_routes, workspace_member_routes
from app.main import app


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Connection:
    def __init__(self, *, actor_role=None, target_role=None, account_email=None):
        self.actor_role = actor_role
        self.target_role = target_role
        self.account_email = account_email
        self.executed = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        if "SELECT id FROM workspaces" in query:
            return {"id": args[0]}
        if "SELECT role,status FROM workspace_memberships" in query:
            return {"role": self.actor_role, "status": "active"}
        if "SELECT m.role,m.status,u.status AS account_status" in query:
            return {
                "role": self.target_role,
                "status": "active",
                "account_status": "active",
                "email_verified_at": "2026-01-01T00:00:00+00:00",
            }
        return None

    async def fetchval(self, query, *args):
        if "SELECT email FROM app_users" in query:
            return self.account_email
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "UPDATE 1"


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def _authenticated_platform_admin_session():
    async def authenticate(request):
        return None, None, {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "email": "customer@example.test",
        }
    return authenticate


def test_workspace_member_cannot_escalate_own_role_via_http(monkeypatch):
    actor_id = "00000000-0000-0000-0000-000000000001"
    target_id = "00000000-0000-0000-0000-000000000002"
    connection = _Connection(actor_role="member", target_role="viewer")

    async def authenticated(request, workspace_id, *, csrf=False):
        return {"user_id": actor_id}

    monkeypatch.setattr(workspace_member_routes, "_authorized_session", authenticated)
    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        response = client.patch(
            f"/api/v1/workspaces/members/{target_id}",
            json={"workspace_id": "tenant-a", "role": "admin"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "workspace_admin_required"
    assert not any("UPDATE workspace_memberships" in query for query, _ in connection.executed)


def test_non_allowlisted_account_cannot_access_platform_admin_http_routes(monkeypatch):
    connection = _Connection(account_email="customer@example.test")
    monkeypatch.setattr(
        platform_admin_routes, "_authenticated", _authenticated_platform_admin_session()
    )
    monkeypatch.setattr(
        platform_admin_routes.settings, "platform_admin_emails", "owner@example.test"
    )

    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        response = client.get("/api/v1/platform-admin/overview")

    assert response.status_code == 403
    assert response.json()["detail"] == "platform_admin_required"


def test_platform_admin_routes_fail_closed_when_allowlist_is_empty(monkeypatch):
    connection = _Connection(account_email="owner@example.test")
    monkeypatch.setattr(
        platform_admin_routes, "_authenticated", _authenticated_platform_admin_session()
    )
    monkeypatch.setattr(platform_admin_routes.settings, "platform_admin_emails", "")

    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        response = client.get("/api/v1/platform-admin/overview")

    assert response.status_code == 503
    assert response.json()["detail"] == "platform_admin_allowlist_not_configured"
    assert not connection.executed


def test_workspace_member_cannot_read_another_tenants_members_via_http(monkeypatch):
    async def authenticate(request):
        return None, None, {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "email": "tenant-a@example.test",
        }

    class _DenyCrossTenant:
        async def authorize_workspace(self, **kwargs):
            assert kwargs["workspace_id"] == "tenant-b"
            return False

    monkeypatch.setattr(workspace_member_routes, "_authenticated", authenticate)
    with TestClient(app) as client:
        app.state.auth_store = _DenyCrossTenant()
        response = client.get(
            "/api/v1/workspaces/members?workspace_id=tenant-b"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "workspace_not_found"
