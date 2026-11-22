import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.api import workspace_invitation_routes
from app.services.auth_security import token_digest


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Connection:
    def __init__(self, active_memberships, account_exists=True, invitation_role="member"):
        self.active_memberships = active_memberships
        self.account_exists = account_exists
        self.invitation_role = invitation_role
        self.calls = []
        self.token = "t" * 43

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "FROM workspaces WHERE id=$1 FOR UPDATE" in query:
            return {"id": "workspace-test"}
        if "FROM workspace_invitations WHERE token_sha256" in query:
            return {
                "id": UUID("00000000-0000-0000-0000-000000000010"),
                "workspace_id": "workspace-test",
                "invited_email": "person@example.test",
                "role": self.invitation_role,
                "status": "pending",
                "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
            }
        if "FROM app_users WHERE id=$1 FOR UPDATE" in query:
            return {"id": args[0], "status": "active", "email_verified_at": datetime.now(timezone.utc)} if self.account_exists else None
        if "FROM workspace_memberships" in query:
            return None
        return None

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "SELECT workspace_id FROM workspace_invitations" in query:
            return "workspace-test"
        return self.active_memberships

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
    async def authenticated(request):
        return None, None, {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "email": "person@example.test",
        }

    monkeypatch.setattr(workspace_invitation_routes, "_authenticated", authenticated)
    monkeypatch.setattr(workspace_invitation_routes, "_check_csrf", lambda request, session: None)
    monkeypatch.setattr(workspace_invitation_routes, "_pool", lambda request: _Pool(connection))


def test_invitation_acceptance_obeys_workspace_limit(monkeypatch):
    connection = _Connection(active_memberships=10)
    _configure(monkeypatch, connection)
    payload = workspace_invitation_routes.InvitationAccept(token=connection.token)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(workspace_invitation_routes.accept_invitation(payload, SimpleNamespace()))

    assert exc.value.status_code == 429
    assert exc.value.detail == "workspace_limit_reached"
    assert any(call[0] == "fetchrow" and "FOR UPDATE" in call[1] for call in connection.calls)
    assert not any(call[0] == "execute" and "INSERT INTO workspace_memberships" in call[1] for call in connection.calls)


def test_invitation_acceptance_allows_membership_below_limit(monkeypatch):
    connection = _Connection(active_memberships=9)
    _configure(monkeypatch, connection)
    payload = workspace_invitation_routes.InvitationAccept(token=connection.token)

    result = asyncio.run(workspace_invitation_routes.accept_invitation(payload, SimpleNamespace()))

    assert result["workspace_id"] == "workspace-test"
    assert any(call[0] == "execute" and "INSERT INTO workspace_memberships" in call[1] for call in connection.calls)



def test_invitation_acceptance_rejects_missing_account_without_membership_insert(monkeypatch):
    connection = _Connection(active_memberships=0, account_exists=False)
    _configure(monkeypatch, connection)
    payload = workspace_invitation_routes.InvitationAccept(token=connection.token)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(workspace_invitation_routes.accept_invitation(payload, SimpleNamespace()))

    assert exc.value.status_code == 401
    assert exc.value.detail == "account_unavailable"
    assert not any(call[0] == "execute" and "INSERT INTO workspace_memberships" in call[1] for call in connection.calls)
    assert not any(call[0] == "execute" and "SET status='accepted'" in call[1] for call in connection.calls)
