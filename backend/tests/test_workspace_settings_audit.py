import asyncio
from types import SimpleNamespace

from app.api import workspace_settings_routes


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Connection:
    def __init__(self):
        self.calls = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return {"id": args[0], "name": args[1], "created_at": "2026-10-28T00:00:00Z"}

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "INSERT 0 1"


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


def test_workspace_settings_update_audits_change(monkeypatch):
    connection = _Connection()

    async def authorize(request, workspace_id, *, write=False):
        assert workspace_id == "workspace-test"
        assert write
        return {"user_id": "00000000-0000-0000-0000-000000000001"}

    monkeypatch.setattr(workspace_settings_routes, "_authorized", authorize)
    monkeypatch.setattr(workspace_settings_routes, "_pool", lambda request: _Pool(connection))
    request = SimpleNamespace()
    payload = workspace_settings_routes.WorkspaceSettingsUpdate(
        workspace_id="workspace-test",
        name="Updated workspace",
    )

    result = asyncio.run(workspace_settings_routes.update_workspace_settings(payload, request))

    assert result["name"] == "Updated workspace"
    assert len(connection.calls) == 2
    assert connection.calls[0][0] == "fetchrow"
    assert connection.calls[1][0] == "execute"
    assert "workspace.settings.updated" in connection.calls[1][1]
    assert '"changed_fields": ["name"]' in connection.calls[1][2][2]
