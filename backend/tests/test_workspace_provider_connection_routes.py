from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api import auth_routes
from app.main import app
from app.services.auth_http_security import csrf_token_digest

CSRF = "c" * 43
SESSION = "s" * 43
USER_ID = "00000000-0000-0000-0000-000000000001"


class FakeAuthStore:
    def __init__(self, role="admin"):
        self.role = role

    async def authenticate_session(self, token):
        if token != SESSION:
            return None
        return {"user_id": USER_ID, "email": "member@example.test", "session_id": "session-test",
                "expires_at": datetime.now(timezone.utc), "csrf_token_sha256": csrf_token_digest(CSRF)}

    async def authorize_workspace(self, *, user_id, workspace_id, minimum_role):
        roles = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}
        return workspace_id == "workspace-a" and roles[self.role] >= roles[minimum_role]


class AllowLimiter:
    async def consume(self, **kwargs):
        return {"allowed": True, "remaining": 5, "reset_at": datetime.now(timezone.utc)}


class FakeProviderConnectionStore:
    def __init__(self):
        self.rows = []
        self.created = None

    async def list_for_workspace(self, **kwargs):
        return self.rows

    async def create_pending(self, **kwargs):
        self.created = kwargs
        return {"id": "connection-id", **kwargs, "status": "pending"}

    async def cancel_pending(self, **kwargs):
        self.cancelled = kwargs
        return {"id": str(kwargs["connection_id"]), "status": "revoked",
                "provider": "email", "display_label": "Marketing mailbox"}


def setup(monkeypatch, client, role="admin"):
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    app.state.auth_store = FakeAuthStore(role)
    app.state.auth_rate_limiter = AllowLimiter()
    app.state.workspace_provider_connection_store = FakeProviderConnectionStore()
    client.cookies.set("__Host-oma_session", SESSION)
    client.cookies.set("__Host-oma_csrf", CSRF)


def test_connection_intent_requires_admin_and_csrf(monkeypatch):
    payload = {"provider": "email", "display_label": "Marketing mailbox"}
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, "member")
        denied = client.post("/api/v1/workspaces/workspace-a/provider-connections",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF}, json=payload)
        setup(monkeypatch, client, "admin")
        no_csrf = client.post("/api/v1/workspaces/workspace-a/provider-connections",
            headers={"Origin": "https://app.example.test"}, json=payload)
        created = client.post("/api/v1/workspaces/workspace-a/provider-connections",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF}, json=payload)
    assert denied.status_code == 404
    assert no_csrf.status_code == 403
    assert created.status_code == 201
    assert created.json()["connection"]["status"] == "pending"
    assert "secret_reference" not in created.json()["connection"]
    assert "not yet available" in created.json()["message"]


def test_connection_intent_rejects_secrets_and_unknown_fields(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, "admin")
        extra = client.post("/api/v1/workspaces/workspace-a/provider-connections",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"provider": "email", "display_label": "Mail", "access_token": "never-accept"})
        invalid = client.post("/api/v1/workspaces/workspace-a/provider-connections",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"provider": "sms", "display_label": "Unsupported"})
    assert extra.status_code == 422
    assert invalid.status_code == 422


def test_connection_list_is_workspace_scoped_and_never_claims_sending(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, "viewer")
        response = client.get("/api/v1/workspaces/workspace-a/provider-connections")
    assert response.status_code == 200
    assert response.json()["connections"] == []
    assert response.json()["sending_enabled"] is False

def test_store_public_projection_drops_secret_reference_and_credentials():
    from app.services.workspace_provider_connection_store import WorkspaceProviderConnectionStore

    row = {
        "id": "connection-id",
        "workspace_id": "workspace-a",
        "provider": "email",
        "display_label": "Marketing mailbox",
        "status": "pending",
        "secret_reference": "vault://provider/opaque-reference",
        "access_token": "must-never-leak",
        "created_by": USER_ID,
        "created_at": datetime(2026, 10, 21, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 10, 21, tzinfo=timezone.utc),
        "granted_scopes": [],
        "token_expires_at": None,
        "last_validated_at": None,
        "last_error_code": None,
        "revoked_at": None,
    }
    public = WorkspaceProviderConnectionStore._public(row)
    assert public["id"] == "connection-id"
    assert "secret_reference" not in public
    assert "access_token" not in public


def test_cancel_pending_intent_requires_admin_and_csrf(monkeypatch):
    connection_id = "00000000-0000-0000-0000-000000000099"
    path = f"/api/v1/workspaces/workspace-a/provider-connections/{connection_id}/cancel"
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, "member")
        denied = client.post(path, headers={"Origin": "https://app.example.test",
                                             "X-CSRF-Token": CSRF})
        setup(monkeypatch, client, "admin")
        no_csrf = client.post(path, headers={"Origin": "https://app.example.test"})
        cancelled = client.post(path, headers={"Origin": "https://app.example.test",
                                                "X-CSRF-Token": CSRF})
    assert denied.status_code == 404
    assert no_csrf.status_code == 403
    assert cancelled.status_code == 200
    assert cancelled.json()["connection"]["status"] == "revoked"
    assert "does not revoke credentials at a provider" in cancelled.json()["message"]
