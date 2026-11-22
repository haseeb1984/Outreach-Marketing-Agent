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
    def __init__(self, active_workspaces, account_exists=True):
        self.active_workspaces = active_workspaces
        self.account_exists = account_exists
        self.calls = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query))
        return {"id": args[0]} if "FOR UPDATE" in query and self.account_exists else None

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query))
        return []

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

    async def close(self):
        return None


class _AuthStore:
    async def authorize_workspace(self, **kwargs):
        return True


def _configure_request(monkeypatch, active_workspaces, account_exists=True):
    user_id = "00000000-0000-0000-0000-000000000001"
    monkeypatch.setattr(
        workspace_routes,
        "_authenticated",
        _fake_authenticated(user_id),
    )
    monkeypatch.setattr(workspace_routes, "_check_csrf", lambda request, session: None)
    connection = _Connection(active_workspaces, account_exists=account_exists)
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



def test_invitation_list_query_uses_real_sql_newlines(monkeypatch):
    from app.api import workspace_invitation_routes

    async def authenticate(request):
        return None, None, {"user_id": "00000000-0000-0000-0000-000000000001", "email": "owner@example.test"}

    async def authorize(request, workspace_id, session):
        return None

    monkeypatch.setattr(workspace_invitation_routes, "_authenticated", authenticate)
    monkeypatch.setattr(workspace_invitation_routes, "_authorize_admin", authorize)
    class _InvitationListConnection:
        def __init__(self):
            self.calls = []

        def transaction(self):
            return _Transaction()

        async def fetchrow(self, query, *args):
            self.calls.append(("fetchrow", query, args))
            return {"id": args[0]}

        async def fetchval(self, query, *args):
            self.calls.append(("fetchval", query, args))
            return "owner"

        async def fetch(self, query, *args):
            self.calls.append(("fetch", query, args))
            return []

    connection = _InvitationListConnection()
    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        response = client.get("/api/v1/workspaces/invitations?workspace_id=workspace-test")

    assert response.status_code == 200
    query = next(call[1] for call in connection.calls if call[0] == "fetch")
    assert "CASE WHEN status='pending'" in query
    assert "\\n" not in query


def test_workspace_creation_rejects_missing_account_row(monkeypatch):
    _user_id, connection = _configure_request(
        monkeypatch, active_workspaces=0, account_exists=False
    )
    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        app.state.auth_store = _AuthStore()
        response = client.post(
            "/api/v1/workspaces",
            json={"name": "Orphan workspace"},
            headers={"Origin": "https://app.example.test"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "account_unavailable"
    assert not any(call[0] == "execute" and "INSERT INTO workspaces" in call[1] for call in connection.calls)


def test_invitation_revocation_locks_and_rechecks_actor_membership(monkeypatch):
    from app.api import workspace_invitation_routes

    class _RevokeConnection:
        def __init__(self):
            self.calls = []

        def transaction(self):
            return _Transaction()

        async def fetchrow(self, query, *args):
            self.calls.append(("fetchrow", query, args))
            assert "workspaces" in query and "FOR UPDATE" in query
            return {"id": args[0]}

        async def fetchval(self, query, *args):
            self.calls.append(("fetchval", query, args))
            assert "FOR UPDATE" in query
            assert "status='active'" in query
            return "owner"

        async def execute(self, query, *args):
            self.calls.append(("execute", query, args))
            return "UPDATE 1"

    async def authenticate(request):
        return None, None, {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "email": "owner@example.test",
        }

    async def authorize(request, workspace_id, session):
        return None

    monkeypatch.setattr(workspace_invitation_routes, "_authenticated", authenticate)
    monkeypatch.setattr(workspace_invitation_routes, "_check_csrf", lambda request, session: None)
    monkeypatch.setattr(workspace_invitation_routes, "_authorize_admin", authorize)
    connection = _RevokeConnection()

    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        response = client.delete(
            "/api/v1/workspaces/invitations/00000000-0000-0000-0000-000000000002?workspace_id=workspace-test",
            headers={"Origin": "https://app.example.test"},
        )

    assert response.status_code == 200
    membership_index = next(i for i, call in enumerate(connection.calls) if call[0] == "fetchval")
    update_index = next(i for i, call in enumerate(connection.calls) if call[0] == "execute")
    assert membership_index < update_index
    assert "workspace_invitations" in connection.calls[update_index][1]


def test_invitation_revocation_rejects_actor_after_role_downgrade(monkeypatch):
    from app.api import workspace_invitation_routes

    class _RevokedActorConnection:
        def __init__(self):
            self.calls = []

        def transaction(self):
            return _Transaction()

        async def fetchrow(self, query, *args):
            self.calls.append(("fetchrow", query, args))
            assert "workspaces" in query and "FOR UPDATE" in query
            return {"id": args[0]}

        async def fetchval(self, query, *args):
            self.calls.append(("fetchval", query, args))
            return "member"

        async def execute(self, query, *args):
            self.calls.append(("execute", query, args))
            return "UPDATE 1"

    async def authenticate(request):
        return None, None, {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "email": "member@example.test",
        }

    async def authorize(request, workspace_id, session):
        # Simulate stale authorization cache: DB recheck must still deny the write.
        return None

    monkeypatch.setattr(workspace_invitation_routes, "_authenticated", authenticate)
    monkeypatch.setattr(workspace_invitation_routes, "_check_csrf", lambda request, session: None)
    monkeypatch.setattr(workspace_invitation_routes, "_authorize_admin", authorize)
    connection = _RevokedActorConnection()

    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        response = client.delete(
            "/api/v1/workspaces/invitations/00000000-0000-0000-0000-000000000002?workspace_id=workspace-test",
            headers={"Origin": "https://app.example.test"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "workspace_not_found"
    assert not any(call[0] == "execute" and "workspace_invitations" in call[1] for call in connection.calls)


def test_invitation_lifecycle_audit_records_all_transitions_without_tokens():
    from app.api import workspace_invitation_routes

    source = workspace_invitation_routes.__file__
    content = open(source, encoding="utf-8").read()
    for event in (
        "workspace.invitation.created",
        "workspace.invitation.accepted",
        "workspace.invitation.revoked",
        "workspace.invitation.expired",
        "workspace.invitation.email_failed",
    ):
        assert event in content
    assert "json.dumps({\"invitation_id\": str(invitation_id)" in content


def test_workspace_settings_update_locks_workspace_before_membership():
    from pathlib import Path

    source = Path(workspace_routes.__file__).parent / "workspace_settings_routes.py"
    content = source.read_text(encoding="utf-8")
    workspace_lock = content.index("SELECT id FROM workspaces WHERE id=$1 FOR UPDATE")
    membership_lock = content.index("SELECT role,status FROM workspace_memberships")
    assert workspace_lock < membership_lock


def test_workspace_member_writes_serialize_with_ownership_transfer_and_audit_roles():
    from pathlib import Path

    source = Path(workspace_routes.__file__).parent / "workspace_member_routes.py"
    content = source.read_text(encoding="utf-8")
    assert content.count("SELECT id FROM workspaces WHERE id=$1 FOR UPDATE") >= 2
    assert "admin_requires_active_verified_account" in content
    assert "previous_role" in content
    assert "FOR UPDATE OF m,u" in content
    assert "workspace.member.role_changed" in content
    assert "workspace.member.removed" in content


def test_workspace_member_listing_includes_account_lifecycle_fields():
    from pathlib import Path

    source = Path(workspace_routes.__file__).parent / "workspace_member_routes.py"
    content = source.read_text(encoding="utf-8")
    for field in ("account_status", "email_verified_at", "last_login_at"):
        assert field in content


def test_invitation_creation_blocks_active_members_and_acceptance_requires_verified_active_account():
    from pathlib import Path
    from app.api import workspace_invitation_routes

    content = Path(workspace_invitation_routes.__file__).read_text(encoding="utf-8")
    assert "already_workspace_member" in content
    assert "email_verification_required" in content
    assert "SELECT id,status,email_verified_at FROM app_users WHERE id=$1 FOR UPDATE" in content
    assert "SELECT id FROM workspaces WHERE id=$1 FOR UPDATE" in content


def test_suspended_members_can_be_revoked_but_not_role_changed():
    from pathlib import Path

    source = Path(workspace_routes.__file__).parent / "workspace_member_routes.py"
    content = source.read_text(encoding="utf-8")
    assert 'target["status"] not in {"active", "suspended"}' in content
    assert 'target["status"] != "active"' in content


class _OwnershipTransferConnection:
    def __init__(self, *, actor_role="owner", actor_status="active",
                 target_role="member", target_status="active", target_exists=True):
        self.actor_role = actor_role
        self.actor_status = actor_status
        self.target_role = target_role
        self.target_status = target_status
        self.target_exists = target_exists
        self.calls = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "FROM workspaces" in query:
            return {"id": args[0]}
        if "FROM workspace_memberships" in query and "JOIN app_users" not in query:
            return {"role": self.actor_role, "status": self.actor_status}
        if "JOIN app_users" in query:
            if not self.target_exists:
                return None
            return {"role": self.target_role, "status": self.target_status}
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "UPDATE 1" if query.lstrip().startswith("UPDATE") else "INSERT 1"


def _configure_ownership_transfer(monkeypatch, connection):
    actor_id = "00000000-0000-0000-0000-000000000001"
    async def authenticate(request):
        return None, None, {"user_id": actor_id, "email": "owner@example.test"}
    monkeypatch.setattr(workspace_routes, "_authenticated", authenticate)
    monkeypatch.setattr(workspace_routes, "_check_csrf", lambda request, session: None)
    return actor_id


def test_ownership_transfer_promotes_verified_active_member_and_audits(monkeypatch):
    from uuid import UUID

    connection = _OwnershipTransferConnection()
    actor_id = _configure_ownership_transfer(monkeypatch, connection)
    target_id = "00000000-0000-0000-0000-000000000002"
    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        response = client.post(
            "/api/v1/workspaces/workspace-test/transfer-ownership",
            headers={"Origin": "https://app.example.test"},
            json={"target_user_id": target_id},
        )

    assert response.status_code == 200
    assert response.json()["previous_owner_role"] == "admin"
    assert response.json()["new_owner_role"] == "owner"
    target_lookup = next(call for call in connection.calls
                         if call[0] == "fetchrow" and "JOIN app_users" in call[1])
    assert "u.status='active'" in target_lookup[1]
    assert "u.email_verified_at IS NOT NULL" in target_lookup[1]
    assert "FOR UPDATE OF m,u" in target_lookup[1]
    updates = [call for call in connection.calls if call[0] == "execute"]
    assert len(updates) == 3
    assert "role='admin'" in updates[0][1]
    assert "role='owner'" in updates[1][1]
    assert "workspace.ownership.transferred" in updates[2][1]
    assert UUID(actor_id) == updates[0][2][1]
    assert updates[1][2][1] == UUID(target_id)


def test_ownership_transfer_requires_current_owner_and_performs_no_writes(monkeypatch):
    connection = _OwnershipTransferConnection(actor_role="admin")
    _configure_ownership_transfer(monkeypatch, connection)
    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        response = client.post(
            "/api/v1/workspaces/workspace-test/transfer-ownership",
            headers={"Origin": "https://app.example.test"},
            json={"target_user_id": "00000000-0000-0000-0000-000000000002"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "workspace_owner_required"
    assert not any(call[0] == "execute" for call in connection.calls)


def test_ownership_transfer_rejects_missing_or_inactive_target_without_writes(monkeypatch):
    for options in (
        {"target_exists": False},
        {"target_status": "suspended"},
    ):
        connection = _OwnershipTransferConnection(**options)
        _configure_ownership_transfer(monkeypatch, connection)
        with TestClient(app) as client:
            app.state.db_pool = _Pool(connection)
            response = client.post(
                "/api/v1/workspaces/workspace-test/transfer-ownership",
                headers={"Origin": "https://app.example.test"},
                json={"target_user_id": "00000000-0000-0000-0000-000000000002"},
            )
        assert response.status_code == 404
        assert response.json()["detail"] == "workspace_member_not_found"
        assert not any(call[0] == "execute" for call in connection.calls)


def test_ownership_transfer_rejects_self_transfer_before_database_access(monkeypatch):
    connection = _OwnershipTransferConnection()
    actor_id = _configure_ownership_transfer(monkeypatch, connection)
    with TestClient(app) as client:
        app.state.db_pool = _Pool(connection)
        response = client.post(
            "/api/v1/workspaces/workspace-test/transfer-ownership",
            headers={"Origin": "https://app.example.test"},
            json={"target_user_id": actor_id},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "ownership_transfer_target_must_be_another_member"
    assert connection.calls == []
