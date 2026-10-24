from fastapi.testclient import TestClient

from app.main import app


def test_customer_dashboard_is_responsive_noindex_and_no_store():
    with TestClient(app) as client:
        response = client.get("/app")

    assert response.status_code == 200
    assert 'name="viewport"' in response.text
    assert 'name="robots" content="noindex,nofollow"' in response.text
    assert 'id="auth-form"' in response.text
    assert 'id="dashboard-view"' in response.text
    assert 'id="campaign-form"' in response.text
    assert 'id="prospect-form"' in response.text
    assert 'id="research-form"' in response.text
    assert 'id="website-audit-heading"' in response.text
    assert 'id="projects-heading"' in response.text
    assert 'id="project-form"' in response.text
    assert 'id="projects-list"' in response.text
    assert "/api/v1/projects?workspace_id=" in response.text
    assert 'id="invitations-heading"' in response.text
    assert 'id="invitation-accept-heading"' in response.text
    assert 'id="invitation-accept-button"' in response.text
    assert "/api/v1/workspaces/invitations/accept" in response.text
    assert "invite_token" in response.text
    assert 'id="invitation-form"' in response.text
    assert 'id="invitations-list"' in response.text
    assert 'id="workspace-admin-heading"' in response.text
    assert 'id="workspace-settings-form"' in response.text
    assert "/api/v1/workspaces/settings?workspace_id=" in response.text
    assert 'id="workspace-members-list"' in response.text
    assert "/api/v1/workspaces/members?workspace_id=" in response.text
    assert "Role changes and removals are permission-checked by the server." in response.text
    assert "/api/v1/workspaces/invitations?workspace_id=" in response.text
    assert 'id="account-export-link"' in response.text
    assert '/api/v1/account/export' in response.text
    assert 'id="domain-challenge-form"' in response.text
    assert 'id="domain-verify-form"' in response.text
    assert 'id="website-audit-form"' in response.text
    assert 'id="website-audit-results"' in response.text
    assert "/api/v1/website-audits" in response.text
    assert "/api/v1/domains/challenges" in response.text
    assert "/api/v1/domains/verify" in response.text
    assert "read-only audit" in response.text.lower()
    assert "/api/v1/research/prospects/search" in response.text
    assert "Review in CRM form" in response.text
    assert "Search results are unverified leads" in response.text
    assert 'id="deliveries-list"' in response.text
    assert 'id="integration-status"' in response.text
    assert 'id="analytics-heading"' in response.text
    assert 'id="analytics-period"' in response.text
    assert 'id="analytics-metrics"' in response.text
    assert "/api/v1/analytics/summary?workspace_id=" in response.text
    assert 'id="integration-refresh"' in response.text
    assert 'id="smtp-connection-test"' in response.text
    assert "/api/v1/integrations/status?workspace_id=" in response.text
    assert "/api/v1/integrations/smtp/test?workspace_id=" in response.text
    assert "No email will be sent." in response.text
    assert 'id="drafts-list"' in response.text
    assert "credentials:'same-origin'" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_workspace_listing_requires_configured_authentication():
    with TestClient(app) as client:
        response = client.get("/api/v1/workspaces")

    assert response.status_code == 503
    assert response.json() == {"detail": "authentication_not_configured"}
