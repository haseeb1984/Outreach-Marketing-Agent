from fastapi.testclient import TestClient

from app.main import app


def test_analytics_summary_fails_closed_without_authentication():
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/analytics/summary",
            params={"workspace_id": "workspace-test"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "authentication_not_configured"}



def test_analytics_summary_rejects_invalid_period_before_database_access():
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/analytics/summary",
            params={"workspace_id": "workspace-test", "since_days": "366"},
        )

    assert response.status_code == 422
