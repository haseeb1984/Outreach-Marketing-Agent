from fastapi.testclient import TestClient

from app.main import app


def test_liveness_does_not_claim_database_readiness():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_readiness_fails_closed_when_database_is_not_configured():
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "not_ready",
            "reason": "database_not_configured",
        }
