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
