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



def test_analytics_summary_hides_workspace_from_nonmembers(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException
    import app.api.analytics_routes as analytics

    class AuthStore:
        async def authorize_workspace(self, **kwargs):
            return False

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                auth_store=AuthStore(),
                db_pool=object(),
            )
        )
    )

    async def authenticated(_request):
        return AuthStore(), "session", {"user_id": "user-1"}

    monkeypatch.setattr(analytics, "_authenticated", authenticated)

    try:
        asyncio.run(
            analytics.analytics_summary(
                request, workspace_id="other-workspace", since_days=30
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "workspace_not_found"
    else:
        raise AssertionError("workspace access must be denied")


def test_analytics_summary_returns_persisted_counts_without_claiming_roi(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import app.api.analytics_routes as analytics

    expected = {
        "prospects_total": 12,
        "prospects_qualified": 4,
        "prospects_replied": 2,
        "prospects_converted": 1,
        "campaigns_active": 2,
        "drafts_pending_approval": 3,
        "drafts_approved": 5,
        "emails_marked_sent": 7,
        "deliveries_failed": 1,
        "deliveries_uncertain": 0,
        "deliveries_pending": 2,
        "inbound_replies": 2,
    }

    class AuthStore:
        async def authorize_workspace(self, **kwargs):
            return True

    class Connection:
        async def fetchrow(self, query, workspace_id, since_days):
            assert "outreach_conversation_messages" in query
            assert workspace_id == "workspace-1"
            assert since_days == 7
            return expected

    class Acquire:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *args):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                auth_store=AuthStore(),
                db_pool=Pool(),
            )
        )
    )

    async def authenticated(_request):
        return AuthStore(), "session", {"user_id": "user-1"}

    monkeypatch.setattr(analytics, "_authenticated", authenticated)
    result = asyncio.run(
        analytics.analytics_summary(
            request, workspace_id="workspace-1", since_days=7
        )
    )

    assert result["counts"] == expected
    assert result["period_days"] == 7
    assert "ROI" in result["unavailable_metrics"]
    assert "not proof of inbox delivery" in result["definitions"]["emails_marked_sent"]

def test_campaign_analytics_scopes_draft_counts_to_selected_period(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import app.api.analytics_routes as analytics

    class AuthStore:
        async def authorize_workspace(self, **kwargs):
            return True

    class Connection:
        query = ""

        async def fetch(self, query, workspace_id, since_days, limit):
            self.query = query
            assert workspace_id == "workspace-1"
            assert since_days == 7
            assert limit == 20
            return []

    connection = Connection()

    class Acquire:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, *args):
            return False

    class Pool:
        def acquire(self):
            return Acquire()

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(auth_store=AuthStore(), db_pool=Pool())
        )
    )

    async def authenticated(_request):
        return AuthStore(), "session", {"user_id": "user-1"}

    monkeypatch.setattr(analytics, "_authenticated", authenticated)
    result = asyncio.run(
        analytics.campaign_performance_analytics(
            request, workspace_id="workspace-1", since_days=7, limit=20
        )
    )

    assert result["items"] == []
    query = connection.query
    assert query.count("d.created_at >= now() - ($2::int * interval '1 day')") >= 5
    assert "q.sent_at >= now() - ($2::int * interval '1 day')" in query
    assert "m.occurred_at >= now() - ($2::int * interval '1 day')" in query

def test_campaign_analytics_can_filter_to_one_client_project(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from uuid import UUID
    import app.api.analytics_routes as analytics

    project_id = UUID("00000000-0000-0000-0000-000000000099")
    class AuthStore:
        async def authorize_workspace(self, **kwargs):
            return True
    class Connection:
        async def fetch(self, query, workspace_id, since_days, limit, selected_project):
            assert selected_project == project_id
            assert "c.project_id=$4" in query
            return []
    connection = Connection()
    class Acquire:
        async def __aenter__(self): return connection
        async def __aexit__(self, *args): return False
    class Pool:
        def acquire(self): return Acquire()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(auth_store=AuthStore(), db_pool=Pool())))
    async def authenticated(_request): return AuthStore(), "session", {"user_id":"user-1"}
    monkeypatch.setattr(analytics, "_authenticated", authenticated)
    result = asyncio.run(analytics.campaign_performance_analytics(
        request, workspace_id="workspace-1", since_days=14, limit=20, project_id=project_id
    ))
    assert result["project_id"] == str(project_id)
    assert result["items"] == []
