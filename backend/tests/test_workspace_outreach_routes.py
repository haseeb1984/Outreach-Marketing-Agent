from datetime import datetime, timezone
from uuid import UUID

from fastapi.testclient import TestClient

from app.api import auth_routes
from app.main import app
from app.services.auth_http_security import csrf_token_digest

CSRF = "c" * 43
SESSION = "s" * 43
USER_ID = "00000000-0000-0000-0000-000000000001"
DRAFT_ID = "00000000-0000-0000-0000-000000000099"


class FakeAuthStore:
    def __init__(self, allowed=True, role="admin"):
        self.allowed = allowed
        self.role = role

    async def authenticate_session(self, token):
        if token != SESSION:
            return None
        return {
            "user_id": USER_ID,
            "email": "member@example.test",
            "session_id": "session-test",
            "expires_at": datetime.now(timezone.utc),
            "csrf_token_sha256": csrf_token_digest(CSRF),
        }

    async def authorize_workspace(self, *, user_id, workspace_id, minimum_role):
        assert workspace_id == "workspace-a"
        roles = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}
        return self.allowed and roles[self.role] >= roles[minimum_role]


class AllowLimiter:
    async def consume(self, **kwargs):
        return {"allowed": True, "remaining": 5, "reset_at": datetime.now(timezone.utc)}


class FakeDraftStore:
    def __init__(self):
        self.created = None
        self.reviewed = None
        self.rows = []

    async def create(self, **kwargs):
        self.created = kwargs
        return {"id": DRAFT_ID, "status": "draft_requires_human_review", "sent": False, **kwargs}

    async def list_for_workspace(self, **kwargs):
        return self.rows

    async def review(self, **kwargs):
        self.reviewed = kwargs
        if kwargs["decision"] != "approved":
            return None
        return {"id": DRAFT_ID, "status": "approved", "reviewed_by": kwargs["reviewer_id"]}


def setup(monkeypatch, client, *, allowed=True, role="admin"):
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    app.state.auth_store = FakeAuthStore(allowed=allowed, role=role)
    app.state.auth_rate_limiter = AllowLimiter()
    app.state.workspace_outreach_draft_store = FakeDraftStore()
    client.cookies.set("__Host-oma_session", SESSION)
    client.cookies.set("__Host-oma_csrf", CSRF)


def payload(channel="email"):
    return {
        "channel": channel,
        "client_business": "Acme SEO",
        "client_offer": "technical SEO audits",
        "prospect_name": "Example Shop",
        "prospect_evidence_url": "https://example.com/about",
        "verified_relevance": "The public site lists two locations.",
        "verified_facts": ["The site lists two locations."],
        "call_to_action": "a short introductory call",
        "whatsapp_opt_in_confirmed": channel == "whatsapp",
    }


def test_create_outreach_draft_requires_csrf_and_member_role(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, role="viewer")
        denied = client.post(
            "/api/v1/workspaces/workspace-a/outreach-drafts",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json=payload(),
        )
        setup(monkeypatch, client, role="member")
        no_csrf = client.post(
            "/api/v1/workspaces/workspace-a/outreach-drafts",
            headers={"Origin": "https://app.example.test"},
            json=payload(),
        )
        created = client.post(
            "/api/v1/workspaces/workspace-a/outreach-drafts",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json=payload(),
        )
    assert denied.status_code == 404
    assert no_csrf.status_code == 403
    assert created.status_code == 201
    assert created.json()["draft"]["sent"] is False


def test_whatsapp_draft_requires_documented_opt_in(monkeypatch):
    data = payload("whatsapp")
    data["whatsapp_opt_in_confirmed"] = False
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, role="member")
        response = client.post(
            "/api/v1/workspaces/workspace-a/outreach-drafts",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json=data,
        )
    assert response.status_code == 422


def test_review_is_admin_only_and_records_no_delivery(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, role="member")
        denied = client.post(
            f"/api/v1/workspaces/workspace-a/outreach-drafts/{DRAFT_ID}/review",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"decision": "approved"},
        )
        setup(monkeypatch, client, role="admin")
        approved = client.post(
            f"/api/v1/workspaces/workspace-a/outreach-drafts/{DRAFT_ID}/review",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"decision": "approved", "note": "Reviewed source evidence"},
        )
    assert denied.status_code == 404
    assert approved.status_code == 200
    assert approved.json()["delivery_status"] == "not_sent"
    assert "No message was sent." in approved.json()["message"]


def test_list_drafts_is_workspace_scoped(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup(monkeypatch, client, role="viewer")
        response = client.get("/api/v1/workspaces/workspace-a/outreach-drafts")
    assert response.status_code == 200
    assert response.json()["drafts"] == []
