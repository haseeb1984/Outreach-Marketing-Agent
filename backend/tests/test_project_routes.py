import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import project_routes


USER_ID = "00000000-0000-0000-0000-000000000001"
PROJECT_ID = UUID("00000000-0000-0000-0000-000000000099")


class _Connection:
    def __init__(self, *, rows=None, row=None, execute_result="UPDATE 1"):
        self.calls = []
        self.rows = rows or []
        self.row = row or {
            "id": PROJECT_ID,
            "workspace_id": "workspace-a",
            "name": "Client website",
            "website_url": "https://client.example",
            "business_model": "B2B",
            "target_market": "United Kingdom",
            "language": "English",
            "audience": "Operations leaders",
            "offer": "Workflow software",
            "conversion_goal": "Book a demo",
            "brand_voice": "Clear",
            "competitors": ["https://competitor.example"],
            "status": "active",
            "created_by": UUID(USER_ID),
            "created_at": "2026-11-01T00:00:00Z",
            "updated_at": "2026-11-02T00:00:00Z",
        }
        self.execute_result = execute_result
        self.scalar = 0

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return self.rows

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "FILTER (WHERE status=" in query:
            return {"pending_approval": 0, "approved": 0, "rejected": 0}
        return self.row

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return self.scalar

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return self.execute_result


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


def _patch_auth(monkeypatch, *, role="member"):
    async def authenticated(request):
        return None, None, {"user_id": USER_ID}

    async def authorize(request, workspace_id, minimum_role, session):
        assert workspace_id == "workspace-a"
        assert session["user_id"] == USER_ID
        if role is None or minimum_role != role:
            raise HTTPException(status_code=404, detail="workspace_not_found")

    monkeypatch.setattr(project_routes, "_authenticated", authenticated)
    monkeypatch.setattr(project_routes, "_check_csrf", lambda request, session: None)
    monkeypatch.setattr(project_routes, "_authorize", authorize)


def test_project_input_normalizes_name_and_deduplicates_competitors():
    payload = project_routes.ProjectCreate(
        workspace_id="workspace-a",
        name="  Client website  ",
        website_url="https://client.example",
        competitors=[" https://one.example ", "https://one.example", "https://two.example"],
    )
    assert payload.name == "Client website"
    assert payload.competitors == ["https://one.example", "https://two.example"]


@pytest.mark.parametrize(
    "url",
    [
        "http://client.example",
        "https://user:password@client.example",
        "https://client.example:8443",
        "javascript:alert(1)",
        "https://",
    ],
)
def test_project_website_rejects_unsafe_or_non_https_urls(url):
    with pytest.raises(ValidationError):
        project_routes.ProjectCreate(
            workspace_id="workspace-a",
            name="Client",
            website_url=url,
        )


def test_list_projects_is_workspace_scoped_and_viewer_readable(monkeypatch):
    connection = _Connection(rows=[_Connection().row])

    async def authorize(request, workspace_id, minimum_role, session):
        assert (workspace_id, minimum_role) == ("workspace-a", "viewer")

    async def authenticated(request):
        return None, None, {"user_id": USER_ID}

    monkeypatch.setattr(project_routes, "_authenticated", authenticated)
    monkeypatch.setattr(project_routes, "_authorize", authorize)
    monkeypatch.setattr(project_routes, "_pool", lambda request: _Pool(connection))

    result = asyncio.run(
        project_routes.list_projects(
            SimpleNamespace(), workspace_id="workspace-a", limit=25, offset=10
        )
    )

    assert result["limit"] == 25
    assert result["offset"] == 10
    assert result["items"][0]["id"] == str(PROJECT_ID)
    query, args = connection.calls[0][1], connection.calls[0][2]
    assert "WHERE workspace_id=$1 AND archived_at IS NULL" in query
    assert args == ("workspace-a", 25, 10)


def test_create_project_requires_member_role_csrf_and_workspace_binding(monkeypatch):
    connection = _Connection()
    _patch_auth(monkeypatch, role="member")
    monkeypatch.setattr(project_routes, "_pool", lambda request: _Pool(connection))
    payload = project_routes.ProjectCreate(
        workspace_id="workspace-a",
        name="Client website",
        website_url="https://client.example",
        competitors=["https://competitor.example"],
    )

    result = asyncio.run(project_routes.create_project(payload, SimpleNamespace()))

    assert result["id"] == str(PROJECT_ID)
    query, args = connection.calls[0][1], connection.calls[0][2]
    assert "INSERT INTO workspace_projects" in query
    assert args[0] == "workspace-a"
    assert args[1] == "Client website"
    assert args[-1] == UUID(USER_ID)


def test_update_project_scopes_mutation_to_project_and_workspace(monkeypatch):
    connection = _Connection()
    _patch_auth(monkeypatch, role="member")
    monkeypatch.setattr(project_routes, "_pool", lambda request: _Pool(connection))
    payload = project_routes.ProjectUpdate(
        workspace_id="workspace-a",
        name="Updated client",
        competitors=["https://new-competitor.example"],
    )

    result = asyncio.run(
        project_routes.update_project(PROJECT_ID, payload, SimpleNamespace())
    )

    assert result["id"] == str(PROJECT_ID)
    query, args = connection.calls[0][1], connection.calls[0][2]
    assert "WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL" in query
    assert args[:2] == (PROJECT_ID, "workspace-a")
    assert "name=" in query and "competitors=" in query


def test_update_project_rejects_empty_patch_without_database_access(monkeypatch):
    _patch_auth(monkeypatch, role="member")
    connection = _Connection()
    monkeypatch.setattr(project_routes, "_pool", lambda request: _Pool(connection))
    payload = project_routes.ProjectUpdate(workspace_id="workspace-a")

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            project_routes.update_project(PROJECT_ID, payload, SimpleNamespace())
        )

    assert error.value.status_code == 422
    assert error.value.detail == "no_project_updates_supplied"
    assert connection.calls == []


def test_archive_project_is_soft_deleted_and_workspace_scoped(monkeypatch):
    connection = _Connection(execute_result="UPDATE 1")
    _patch_auth(monkeypatch, role="admin")
    monkeypatch.setattr(project_routes, "_pool", lambda request: _Pool(connection))

    result = asyncio.run(
        project_routes.archive_project(
            PROJECT_ID, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(conversation_store=None))), workspace_id="workspace-a"
        )
    )

    assert result is None
    query, args = connection.calls[0][1], connection.calls[0][2]
    assert "SET status='archived',archived_at=now()" in query
    assert "WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL" in query
    assert args == (PROJECT_ID, "workspace-a")


def test_archive_project_returns_not_found_when_project_is_outside_workspace(monkeypatch):
    connection = _Connection(execute_result="UPDATE 0")
    _patch_auth(monkeypatch, role="admin")
    monkeypatch.setattr(project_routes, "_pool", lambda request: _Pool(connection))

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            project_routes.archive_project(
                PROJECT_ID, SimpleNamespace(), workspace_id="workspace-a"
            )
        )

    assert error.value.status_code == 404
    assert error.value.detail == "project_not_found"


def test_project_overview_is_workspace_scoped_and_returns_linked_workflow_snapshot(monkeypatch):
    connection = _Connection()
    connection.scalar = 7
    _patch_auth(monkeypatch, role="viewer")
    monkeypatch.setattr(project_routes, "_pool", lambda request: _Pool(connection))

    result = asyncio.run(
        project_routes.get_project_overview(
            PROJECT_ID, SimpleNamespace(), workspace_id="workspace-a"
        )
    )

    assert result["project"]["id"] == str(PROJECT_ID)
    assert result["counts"] == {"campaigns": 7, "prospects": 7}
    assert result["recent_limit"] == 10
    assert len(connection.calls) == 11
    assert connection.calls[0][2] == (PROJECT_ID, "workspace-a")
    assert connection.calls[3][2] == ("workspace-a", PROJECT_ID)
    assert "outreach_followup_sequences" in connection.calls[8][1]
    assert "outreach_followup_enrollments" in connection.calls[9][1]
    assert "crm_prospects" in connection.calls[-1][1]
    assert all(call[2][0] == "workspace-a" for call in connection.calls if call[0] in {"fetch", "fetchval"})

def test_project_overview_includes_project_draft_and_outreach_activity(monkeypatch):
    from datetime import datetime, timezone

    connection = _Connection()
    connection.scalar = 2
    _patch_auth(monkeypatch, role="viewer")
    monkeypatch.setattr(project_routes, "_pool", lambda request: _Pool(connection))

    async def fetch(query, *args):
        connection.calls.append(("fetch", query, args))
        if "FROM outreach_drafts d" in query:
            return [{"id": PROJECT_ID, "status": "pending_approval", "channel": "email",
                     "created_at": datetime(2026, 11, 27, tzinfo=timezone.utc),
                     "prospect_name": "A", "campaign_name": "C"}]
        if "FROM outreach_deliveries q" in query:
            return [{"id": PROJECT_ID, "channel": "email", "status": "sent",
                     "activity_at": datetime(2026, 11, 27, tzinfo=timezone.utc),
                     "prospect_name": "A", "campaign_name": "C"}]
        if "FROM whatsapp_outbound_deliveries q" in query:
            return [{"id": PROJECT_ID, "channel": "whatsapp", "status": "delivered",
                     "activity_at": datetime(2026, 11, 26, tzinfo=timezone.utc),
                     "prospect_name": "A", "campaign_name": "C"}]
        return []
    async def fetchrow(query, *args):
        connection.calls.append(("fetchrow", query, args))
        if "FILTER (WHERE status=" in query:
            return {"pending_approval": 1, "approved": 2, "rejected": 0}
        return connection.row
    connection.fetch=fetch
    connection.fetchrow=fetchrow

    result = asyncio.run(project_routes.get_project_overview(
        PROJECT_ID, SimpleNamespace(), workspace_id="workspace-a"
    ))
    assert result["draft_counts"] == {"pending_approval": 1, "approved": 2, "rejected": 0}
    assert result["recent_drafts"][0]["prospect_name"] == "A"
    assert [item["channel"] for item in result["outreach_activity"]] == ["email", "whatsapp"]
    scoped_activity_queries = [call[1] for call in connection.calls if call[0] == "fetch" and ("FROM outreach_drafts d" in call[1] or "FROM outreach_deliveries q" in call[1] or "FROM whatsapp_outbound_deliveries q" in call[1])]
    assert len(scoped_activity_queries) == 3
    assert all("project_id=$2" in query and "$1" in query for query in scoped_activity_queries)
