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

    @asynccontextmanager
    async def transaction(self, **kwargs):
        yield

    async def fetchrow(self, query, *args):
        if "SELECT id,status FROM app_users" in query:
            return {"id": args[0], "status": "active"}
        raise AssertionError("unexpected fetchrow query")

    async def fetchval(self, query, *args):
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


def _authenticated(request):
    return ("user@example.test", None, {"user_id": "00000000-0000-0000-0000-000000000001"})


def test_delete_account_revokes_sessions_pseudonymizes_identity_and_clears_cookies(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(account_routes, "_authenticated", _authenticated)
    monkeypatch.setattr(account_routes, "_check_csrf", lambda request, session: None)
    with TestClient(app) as client:
        app.state.db_pool = FakePool(conn)
        response = client.delete("/api/v1/account")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert "deleted+00000000000000000000000000000001@accounts.invalid" in str(conn.executed)
    assert any("UPDATE auth_sessions SET revoked_at=now()" in sql for sql, _ in conn.executed)
    assert any("UPDATE workspace_memberships SET status='revoked'" in sql for sql, _ in conn.executed)
    assert any("UPDATE app_users" in sql and "status='deleted'" in sql for sql, _ in conn.executed)
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any("__Host-oma_session=;" in value for value in set_cookie_headers)
    assert any("__Host-oma_csrf=;" in value for value in set_cookie_headers)
    assert "Cache-Control" in response.headers


def test_delete_account_refuses_to_orphan_shared_workspace_owner(monkeypatch):
    conn = FakeConnection(blocked=True)
    monkeypatch.setattr(account_routes, "_authenticated", _authenticated)
    monkeypatch.setattr(account_routes, "_check_csrf", lambda request, session: None)
    with TestClient(app) as client:
        app.state.db_pool = FakePool(conn)
        response = client.delete("/api/v1/account")
    assert response.status_code == 409
    assert response.json()["detail"] == "transfer_workspace_ownership_before_account_deletion"
    assert conn.executed == []


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
