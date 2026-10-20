from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api import auth_routes
from app.main import app
from app.services.auth_http_security import csrf_token_digest


CSRF = "c" * 43
SESSION = "s" * 43
USER_ID = "00000000-0000-0000-0000-000000000001"


class FakeAuthStore:
    def __init__(self, *, allowed=True, role="admin"):
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
        assert user_id == USER_ID
        assert workspace_id == "workspace-a"
        roles = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}
        return self.allowed and roles[self.role] >= roles[minimum_role]


class AllowLimiter:
    async def consume(self, **kwargs):
        return {"allowed": True, "remaining": 5, "reset_at": datetime.now(timezone.utc)}


class FakeDomainStore:
    def __init__(self):
        self.issued = None
        self.revoked = None

    async def get_verified_domains(self, *, workspace_id):
        return [{
            "workspace_id": workspace_id,
            "domain": "example.com",
            "status": "verified",
            "verified_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }]

    async def issue_challenge(self, *, workspace_id, domain):
        self.issued = (workspace_id, domain)
        return {
            "challenge": {
                "domain": domain,
                "method": "dns_txt",
                "expires_at": "2026-01-02T00:00:00+00:00",
            },
            "dns_record": {
                "record_name": f"_oma-verify.{domain}",
                "record_value": "outreach-marketing-agent-verification=one-time-secret",
            },
        }

    async def verify_challenge(self, *, workspace_id, domain, txt_values):
        return {
            "verified": "outreach-marketing-agent-verification=valid" in txt_values,
            "reason": "dns_txt_token_matched" if "outreach-marketing-agent-verification=valid" in txt_values else "dns_txt_token_not_found",
        }

    async def revoke_domain(self, *, workspace_id, domain):
        self.revoked = (workspace_id, domain)
        return True


def setup_workspace_app(monkeypatch, client, *, allowed=True, role="admin"):
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    app.state.auth_store = FakeAuthStore(allowed=allowed, role=role)
    app.state.auth_rate_limiter = AllowLimiter()
    app.state.domain_authorization_store = FakeDomainStore()
    client.cookies.set("__Host-oma_session", SESSION)
    client.cookies.set("__Host-oma_csrf", CSRF)


def test_workspace_domains_require_active_membership(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup_workspace_app(monkeypatch, client, allowed=False)
        response = client.get("/api/v1/workspaces/workspace-a/domains")
    assert response.status_code == 404
    assert response.json()["detail"] == "workspace_not_found"


def test_workspace_domain_listing_allows_viewer(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup_workspace_app(monkeypatch, client, role="viewer")
        response = client.get("/api/v1/workspaces/workspace-a/domains")
    assert response.status_code == 200
    assert response.json()["domains"][0]["domain"] == "example.com"


def test_workspace_domain_challenge_requires_csrf_and_admin(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup_workspace_app(monkeypatch, client, role="viewer")
        denied = client.post(
            "/api/v1/workspaces/workspace-a/domains/challenges",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"domain": "example.com"},
        )
    assert denied.status_code == 404

    with TestClient(app, base_url="https://app.example.test") as client:
        setup_workspace_app(monkeypatch, client, role="admin")
        response = client.post(
            "/api/v1/workspaces/workspace-a/domains/challenges",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"domain": "Example.com"},
        )
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.json()["txt_record_name"] == "_oma-verify.example.com"
    assert response.json()["txt_record_value"].startswith(
        "outreach-marketing-agent-verification="
    )


def test_workspace_domain_revocation_requires_csrf(monkeypatch):
    with TestClient(app, base_url="https://app.example.test") as client:
        setup_workspace_app(monkeypatch, client, role="admin")
        response = client.delete(
            "/api/v1/workspaces/workspace-a/domains/example.com",
            headers={"Origin": "https://app.example.test"},
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_validation_failed"

def test_domain_verification_uses_server_dns_not_client_supplied_evidence(monkeypatch):
    from app.api import workspace_domain_routes

    async def fake_resolve(domain):
        assert domain == "example.com"
        return ["outreach-marketing-agent-verification=valid"]

    monkeypatch.setattr(workspace_domain_routes, "_resolve_txt_values", fake_resolve)
    with TestClient(app, base_url="https://app.example.test") as client:
        setup_workspace_app(monkeypatch, client, role="admin")
        response = client.post(
            "/api/v1/workspaces/workspace-a/domains/verify",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"domain": "example.com"},
        )
        forged = client.post(
            "/api/v1/workspaces/workspace-a/domains/verify",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": CSRF},
            json={"domain": "example.com", "txt_values": ["outreach-marketing-agent-verification=valid"]},
        )
    assert response.status_code == 200
    assert response.json()["verified"] is True
    assert forged.status_code == 422
