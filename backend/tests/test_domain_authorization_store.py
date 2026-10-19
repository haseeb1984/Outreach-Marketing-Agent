from contextlib import asynccontextmanager

import asyncio
import pytest

from app.services.domain_authorization_store import DomainAuthorizationStore


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, query, workspace_id):
        assert "workspace_domains" in query
        return [row for row in self.rows if row["workspace_id"] == workspace_id]

class FakePool:
    def __init__(self, rows):
        self.connection = FakeConnection(rows)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_store_authorizes_only_records_loaded_for_authenticated_workspace():
    store = DomainAuthorizationStore(FakePool([
        {"workspace_id": "ws-1", "domain": "client.example", "status": "verified",
         "verified_at": "2026-10-20T00:00:00+00:00", "revoked_at": None},
        {"workspace_id": "ws-2", "domain": "other.example", "status": "verified",
         "verified_at": "2026-10-20T00:00:00+00:00", "revoked_at": None},
    ]))
    result = asyncio.run(store.authorize_url(
        workspace_id="ws-1", url="https://client.example/about"
    ))
    assert result["host"] == "client.example"
    with pytest.raises(PermissionError):
        asyncio.run(store.authorize_url(
            workspace_id="ws-1", url="https://other.example/"
        ))
