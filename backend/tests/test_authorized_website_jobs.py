import asyncio

import pytest

from app.services.authorized_website_jobs import enqueue_authorized_website_scan


class DomainStore:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def authorize_url(self, *, workspace_id, url):
        self.calls.append((workspace_id, url))
        if self.error:
            raise self.error
        return self.result


class Queue:
    def __init__(self):
        self.calls = []

    async def enqueue(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "job-1", "status": "queued"}


def test_authorized_scan_is_queued_with_normalized_url_and_bounds():
    store = DomainStore({
        "workspace_id": "ws-1",
        "url": "https://client.example/",
        "host": "client.example",
    })
    queue = Queue()
    result = asyncio.run(enqueue_authorized_website_scan(
        domain_store=store,
        job_queue=queue,
        workspace_id="ws-1",
        start_url="https://client.example",
        max_pages=10,
        max_depth=1,
        idempotency_key="request-1",
    ))

    assert result == {"id": "job-1", "status": "queued"}
    assert store.calls == [("ws-1", "https://client.example")]
    assert queue.calls == [{
        "workspace_id": "ws-1",
        "job_type": "website_growth_scan",
        "payload": {
            "start_url": "https://client.example/",
            "authorized_domain": "client.example",
            "max_pages": 10,
            "max_depth": 1,
            "authorization": "verified_domain_record",
        },
        "idempotency_key": "request-1",
    }]


def test_unverified_domain_never_creates_job():
    store = DomainStore(error=PermissionError("domain not verified"))
    queue = Queue()
    with pytest.raises(PermissionError, match="domain not verified"):
        asyncio.run(enqueue_authorized_website_scan(
            domain_store=store,
            job_queue=queue,
            workspace_id="ws-1",
            start_url="https://unverified.example/",
        ))
    assert queue.calls == []


def test_cross_workspace_authorization_result_never_creates_job():
    store = DomainStore({
        "workspace_id": "another-workspace",
        "url": "https://client.example/",
        "host": "client.example",
    })
    queue = Queue()
    with pytest.raises(PermissionError, match="workspace mismatch"):
        asyncio.run(enqueue_authorized_website_scan(
            domain_store=store,
            job_queue=queue,
            workspace_id="ws-1",
            start_url="https://client.example/",
        ))
    assert queue.calls == []


@pytest.mark.parametrize(("field", "value"), [
    ("max_pages", 0),
    ("max_pages", 101),
    ("max_pages", True),
    ("max_depth", -1),
    ("max_depth", 6),
    ("max_depth", True),
])
def test_invalid_scan_bounds_rejected_before_authorization(field, value):
    store = DomainStore({
        "workspace_id": "ws-1",
        "url": "https://client.example/",
        "host": "client.example",
    })
    queue = Queue()
    kwargs = {"max_pages": 25, "max_depth": 2}
    kwargs[field] = value
    with pytest.raises(ValueError):
        asyncio.run(enqueue_authorized_website_scan(
            domain_store=store,
            job_queue=queue,
            workspace_id="ws-1",
            start_url="https://client.example/",
            **kwargs,
        ))
    assert store.calls == []
    assert queue.calls == []
