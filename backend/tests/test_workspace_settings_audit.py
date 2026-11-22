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
        if "workspace_memberships" in query:
            return {"role": "owner", "status": "active"}
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
    assert len(connection.calls) == 3
    assert connection.calls[0][0] == "fetchrow"
    assert "workspace_memberships" in connection.calls[0][1]
    assert "FOR UPDATE" in connection.calls[0][1]
    assert connection.calls[1][0] == "fetchrow"
    assert "UPDATE workspaces SET name" in connection.calls[1][1]
    assert connection.calls[2][0] == "execute"
    assert "workspace.settings.updated" in connection.calls[2][1]
    assert '"changed_fields": ["name"]' in connection.calls[2][2][2]

def test_workspace_settings_read_returns_only_the_requested_workspace(monkeypatch):
    connection = _ReadConnection()

    async def authorize(request, workspace_id, *, write=False):
        assert workspace_id == "workspace-read"
        assert write is False
        return {"user_id": "00000000-0000-0000-0000-000000000001"}

    monkeypatch.setattr(workspace_settings_routes, "_authorized", authorize)
    monkeypatch.setattr(workspace_settings_routes, "_pool", lambda request: _Pool(connection))

    result = asyncio.run(
        workspace_settings_routes.get_workspace_settings(
            SimpleNamespace(),
            workspace_id="workspace-read",
        )
    )

    assert result == {
        "workspace_id": "workspace-read",
        "name": "Read workspace",
        "created_at": "2026-10-28T00:00:00Z",
    }
    assert len(connection.calls) == 1
    assert connection.calls[0][0] == "fetchrow"
    assert "WHERE id=$1" in connection.calls[0][1]
    assert connection.calls[0][2] == ("workspace-read",)


class _ReadConnection:
    def __init__(self):
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return {
            "id": args[0],
            "name": "Read workspace",
            "created_at": "2026-10-28T00:00:00Z",
        }


def test_workspace_settings_name_is_trimmed_and_blank_names_are_rejected():
    payload = workspace_settings_routes.WorkspaceSettingsUpdate(
        workspace_id="workspace-read",
        name="  Updated workspace  ",
    )
    assert payload.name == "Updated workspace"

    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        workspace_settings_routes.WorkspaceSettingsUpdate(
            workspace_id="workspace-read",
            name="   ",
        )

