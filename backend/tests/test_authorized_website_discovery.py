import asyncio

import pytest

from app.services import authorized_website_discovery as service


class Store:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def authorize_url(self, *, workspace_id, url):
        self.calls.append((workspace_id, url))
        if self.error:
            raise self.error
        return self.result


def test_authorized_discovery_checks_persisted_domain_before_crawling(monkeypatch):
    store = Store({"url": "https://client.example/", "host": "client.example", "workspace_id": "ws-1"})
    called = []

    async def fake_discover_and_crawl(**kwargs):
        called.append(kwargs)
        return {"crawl": {"pages_crawled": 1}}

    monkeypatch.setattr(service, "discover_and_crawl", fake_discover_and_crawl)
    result = asyncio.run(service.discover_authorized_website(
        store=store, workspace_id="ws-1", start_url="https://client.example/"
    ))

    assert store.calls == [("ws-1", "https://client.example/")]
    assert called == [{"start_url": "https://client.example/", "max_pages": 25, "max_depth": 2}]
    assert result["authorized_domain"] == "client.example"
    assert result["discovery"] == {"crawl": {"pages_crawled": 1}}


def test_unauthorized_domain_is_rejected_before_any_network_discovery(monkeypatch):
    store = Store(error=PermissionError("domain not verified"))
    called = False

    async def fake_discover_and_crawl(**kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(service, "discover_and_crawl", fake_discover_and_crawl)
    with pytest.raises(PermissionError, match="domain not verified"):
        asyncio.run(service.discover_authorized_website(
            store=store, workspace_id="ws-1", start_url="https://unverified.example/"
        ))
    assert called is False


def test_missing_workspace_is_rejected_before_store_or_network(monkeypatch):
    store = Store({"url": "https://client.example/", "host": "client.example", "workspace_id": "ws-1"})
    called = False

    async def fake_discover_and_crawl(**kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(service, "discover_and_crawl", fake_discover_and_crawl)
    with pytest.raises(PermissionError, match="authenticated workspace"):
        asyncio.run(service.discover_authorized_website(
            store=store, workspace_id=" ", start_url="https://client.example/"
        ))
    assert store.calls == []
    assert called is False
