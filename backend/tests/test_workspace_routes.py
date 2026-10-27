from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import workspace_routes
from app.main import app


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Connection:
    def __init__(self, active_workspaces):
        self.active_workspaces = active_workspaces
        self.calls = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query))
        return {"id": args[0]} if "FOR UPDATE" in query else None

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query))
        return self.active_workspaces

    async def execute(self, query, *args):
        self.calls.append(("execute", query))
        return "INSERT 0 1"


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


class _AuthStore:
    async def authorize_workspace(self, **kwargs):
        return True


def _configure_request(monkeypatch, active_workspaces):
    user_id = "00000000-0000-0000-0000-000000000001"
    monkeypatch.setattr(
        workspace_routes,
        "_authenticated",
        _fake_authenticated(user_id),
    )
    monkeypatch.setattr(workspace_routes, "_check_csrf", lambda request, session: None)
    connection = _Connection(active_workspaces)
    return user_id, connection


def _fake_authenticated(user_id):
    async def authenticate(request):
        return None, None, {"user_id": user_id, "email": "owner@example.test"}
    return authenticate


def test_workspace_creation_locks_account_before_checking_limit(monkeypatch):
    user_id, connection = _configure_request(monkeypatch, active_workspaces=9)
    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        app.state.auth_store = _AuthStore()
        response = client.post(
            "/api/v1/workspaces",
            json={"name": "Second workspace"},
            headers={"Origin": "https://app.example.test"},
        )

    assert response.status_code == 201
    lock_index = next(i for i, call in enumerate(connection.calls) if call[0] == "fetchrow" and "FOR UPDATE" in call[1])
    count_index = next(i for i, call in enumerate(connection.calls) if call[0] == "fetchval" and "count(*)" in call[1])
    assert lock_index < count_index
    assert any(call[0] == "execute" and "INSERT INTO workspaces" in call[1] for call in connection.calls)


def test_workspace_creation_limit_rejects_without_inserting(monkeypatch):
    _user_id, connection = _configure_request(monkeypatch, active_workspaces=10)
    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        app.state.auth_store = _AuthStore()
        response = client.post(
            "/api/v1/workspaces",
            json={"name": "Over the limit"},
            headers={"Origin": "https://app.example.test"},
        )

    assert response.status_code == 429
    assert response.json()["detail"] == "workspace_limit_reached"
    assert not any(call[0] == "execute" and "INSERT INTO workspaces" in call[1] for call in connection.calls)
