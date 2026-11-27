from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api import analytics_routes
from app.main import app


class _AuthStore:
    async def authorize_workspace(self, *, user_id, workspace_id, minimum_role):
        return workspace_id == "workspace-a" and minimum_role == "viewer"


class _Connection:
    def __init__(self):
        self.query = ""
        self.args = ()

    async def fetch(self, query, *args):
        self.query = query
        self.args = args
        return [{
            "id": uuid4(),
            "name": "Campaign A",
            "status": "active",
            "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 10, 2, tzinfo=timezone.utc),
            "prospects_in_campaign": 3,
            "drafts_pending_approval": 1,
            "drafts_approved": 2,
            "drafts_rejected": 0,
            "email_sent_marked": 1,
            "email_failed": 0,
            "email_uncertain": 0,
            "email_pending": 1,
            "whatsapp_sent_or_confirmed": 2,
            "whatsapp_delivered": 1,
            "whatsapp_read": 1,
            "whatsapp_failed": 0,
            "whatsapp_uncertain": 0,
            "whatsapp_pending": 0,
            "replies_from_campaign_prospects": 1,
            "converted_stage_prospects": 1,
        }]


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_campaign_analytics_returns_scoped_counts_and_honest_definitions(monkeypatch):
    async def authenticated(_request):
        return None, None, {"user_id": "user-a"}

    connection = _Connection()
    monkeypatch.setattr(analytics_routes, "_authenticated", authenticated)

    with TestClient(app) as client:
        app.state.auth_store = _AuthStore()
        app.state.db_pool = _Pool(connection)
        response = client.get(
            "/api/v1/analytics/campaigns",
            params={"workspace_id": "workspace-a", "since_days": 14},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["period_days"] == 14
    assert body["items"][0]["name"] == "Campaign A"
    assert body["items"][0]["counts"]["email_sent_marked"] == 1
    assert body["items"][0]["counts"]["converted_stage_prospects"] == 1
    assert "not proof of inbox delivery" in body["definitions"]["email_sent_marked"]
    assert "not proof the campaign caused the reply" in body["definitions"]["replies_from_campaign_prospects"]
    assert "c.workspace_id=$1" in connection.query
    assert connection.args == ("workspace-a", 14, 50, None)


def test_campaign_analytics_hides_unknown_workspaces(monkeypatch):
    async def authenticated(_request):
        return None, None, {"user_id": "user-a"}

    connection = _Connection()
    monkeypatch.setattr(analytics_routes, "_authenticated", authenticated)

    with TestClient(app) as client:
        app.state.auth_store = _AuthStore()
        app.state.db_pool = _Pool(connection)
        response = client.get(
            "/api/v1/analytics/campaigns",
            params={"workspace_id": "other-workspace"},
        )

    assert response.status_code == 404
    assert connection.query == ""
