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


class FakeCampaignStore:
    def __init__(self):
        self.created = None
        self.rows = []

    async def create(self, **kwargs):
        self.created = kwargs
        return {"id": "campaign-id", **kwargs, "status": "draft"}

    async def list_for_workspace(self, **kwargs):
        return self.rows


def setup(monkeypatch, client, role="admin"):
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    app.state.auth_store = FakeAuthStore(role)
    app.state.auth_rate_limiter = AllowLimiter()
    app.state.workspace_campaign_store = FakeCampaignStore()
    client.cookies.set("__Host-oma_session", SESSION)
    client.cookies.set("__Host-oma_csrf", CSRF)


def test_create_campaign_requires_member_and_csrf(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, "viewer")
        denied = client.post("/api/v1/workspaces/workspace-a/campaigns",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"name":"Launch", "website_url":"https://example.com", "goal":"sales", "channel":"email"})
        setup(monkeypatch, client, "member")
        no_csrf = client.post("/api/v1/workspaces/workspace-a/campaigns",
            headers={"Origin": "https://app.example.test"},
            json={"name":"Launch", "website_url":"https://example.com", "goal":"sales", "channel":"email"})
        created = client.post("/api/v1/workspaces/workspace-a/campaigns",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"name":"Launch", "website_url":"https://example.com", "goal":"sales", "channel":"email"})
    assert denied.status_code == 404
    assert no_csrf.status_code == 403
    assert created.status_code == 201
    assert created.json()["campaign"]["status"] == "draft"


def test_campaign_rejects_unsafe_url_and_unknown_fields(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, "member")
        unsafe = client.post("/api/v1/workspaces/workspace-a/campaigns",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"name":"Launch", "website_url":"http://127.0.0.1/admin", "goal":"sales", "channel":"email"})
        extra = client.post("/api/v1/workspaces/workspace-a/campaigns",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"name":"Launch", "website_url":"https://example.com", "goal":"sales", "channel":"email", "admin":True})
    assert unsafe.status_code == 422
    assert extra.status_code == 422


def test_list_campaigns_is_workspace_scoped(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, "viewer")
        response = client.get("/api/v1/workspaces/workspace-a/campaigns")
    assert response.status_code == 200
    assert response.json()["campaigns"] == []


def test_campaign_status_transition_requires_admin_and_csrf(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, "member")
        denied = client.post(
            "/api/v1/workspaces/workspace-a/campaigns/00000000-0000-0000-0000-000000000099/status",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"status": "active"},
        )
        setup(monkeypatch, client, "admin")
        no_csrf = client.post(
            "/api/v1/workspaces/workspace-a/campaigns/00000000-0000-0000-0000-000000000099/status",
            headers={"Origin": "https://app.example.test"},
            json={"status": "active"},
        )
    assert denied.status_code == 404
    assert no_csrf.status_code == 403


def test_campaign_status_transition_records_target(monkeypatch):
    class TransitionStore(FakeCampaignStore):
        async def transition_status(self, **kwargs):
            self.transition = kwargs
            return {"id": str(kwargs["campaign_id"]), "status": kwargs["status"]}

    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, "admin")
        app.state.workspace_campaign_store = TransitionStore()
        response = client.post(
            "/api/v1/workspaces/workspace-a/campaigns/00000000-0000-0000-0000-000000000099/status",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"status": "paused"},
        )
    assert response.status_code == 200
    assert response.json()["campaign"]["status"] == "paused"
