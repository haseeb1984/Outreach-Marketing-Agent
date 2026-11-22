import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.api import workspace_member_routes


ACTOR_ID = UUID("00000000-0000-0000-0000-000000000001")
TARGET_ID = UUID("00000000-0000-0000-0000-000000000002")


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Connection:
    def __init__(self, actor_role="owner", target_role="member"):
        self.actor_role = actor_role
        self.target_role = target_role
        self.calls = []
        self.fetchrow_count = 0

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "FROM workspaces WHERE id=$1 FOR UPDATE" in query:
            return {"id": "workspace-test"}
        if "WHERE workspace_id=$1 AND user_id=$2 FOR UPDATE" in query:
            if args[1] == ACTOR_ID:
                return {"role": self.actor_role, "status": "active"}
            return {
                "role": self.target_role,
                "status": "active",
                "account_status": "active",
                "email_verified_at": object(),
            }
        return None

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "UPDATE 1"


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


def _configure(monkeypatch, connection):
    async def authorized_session(request, workspace_id, *, csrf=False):
        return {"user_id": str(ACTOR_ID)}

    monkeypatch.setattr(workspace_member_routes, "_authorized_session", authorized_session)
    monkeypatch.setattr(workspace_member_routes, "_pool", lambda request: _Pool(connection))


def test_admin_cannot_grant_admin_role(monkeypatch):
    connection = _Connection(actor_role="admin", target_role="member")
    _configure(monkeypatch, connection)
    payload = workspace_member_routes.MemberRoleUpdate(
        workspace_id="workspace-test", role="admin"
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            workspace_member_routes.update_workspace_member(
                TARGET_ID, payload, SimpleNamespace()
            )
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "only_owner_can_grant_admin"
    assert not any(call[0] == "execute" for call in connection.calls)


def test_workspace_owner_role_cannot_be_changed(monkeypatch):
    connection = _Connection(actor_role="owner", target_role="owner")
    _configure(monkeypatch, connection)
    payload = workspace_member_routes.MemberRoleUpdate(
        workspace_id="workspace-test", role="member"
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            workspace_member_routes.update_workspace_member(
                TARGET_ID, payload, SimpleNamespace()
            )
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "workspace_owner_role_is_protected"
    assert not any(call[0] == "execute" for call in connection.calls)

def test_admin_cannot_remove_another_admin(monkeypatch):
    connection = _Connection(actor_role="admin", target_role="admin")
    _configure(monkeypatch, connection)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            workspace_member_routes.remove_workspace_member(
                TARGET_ID, SimpleNamespace(), "workspace-test"
            )
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "only_owner_can_remove_admin"
    assert not any(
        call[0] == "execute" and "SET status='revoked'" in call[1]
        for call in connection.calls
    )
    assert not any(
        call[0] == "execute" and "workspace.member.removed" in call[1]
        for call in connection.calls
    )


def test_workspace_owner_cannot_be_removed(monkeypatch):
    connection = _Connection(actor_role="owner", target_role="owner")
    _configure(monkeypatch, connection)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            workspace_member_routes.remove_workspace_member(
                TARGET_ID, SimpleNamespace(), "workspace-test"
            )
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "workspace_owner_cannot_be_removed"
    assert not any(call[0] == "execute" for call in connection.calls)


def test_member_cannot_remove_other_workspace_members(monkeypatch):
    connection = _Connection(actor_role="member", target_role="member")
    _configure(monkeypatch, connection)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            workspace_member_routes.remove_workspace_member(
                TARGET_ID, SimpleNamespace(), "workspace-test"
            )
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "workspace_admin_required"
    assert not any(call[0] == "execute" for call in connection.calls)

