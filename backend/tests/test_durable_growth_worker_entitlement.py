from __future__ import annotations

import asyncio
from uuid import uuid4

from scripts import run_workspace_growth_worker as worker


class _Queue:
    job = None
    failed = None
    last_failed = None

    def __init__(self, _pool):
        pass

    async def claim(self, **_kwargs):
        return self.job

    async def fail(self, **kwargs):
        self.failed = kwargs
        type(self).last_failed = kwargs
        return "failed"


class _Subscriptions:
    async def validate_job_reservation(self, **_kwargs):
        return {"allowed": False, "reason": "subscription_inactive"}


class _Pool:
    pass


def test_worker_does_not_crawl_when_consumed_reservation_is_no_longer_entitled(monkeypatch):
    reservation_id = str(uuid4())
    _Queue.job = {
        "id": str(uuid4()),
        "workspace_id": "trusted-workspace",
        "payload": {
            "start_url": "https://example.com/",
            "business_type": "SaaS",
            "target_market": "US",
            "target_queries": [],
            "max_pages": 10,
            "max_depth": 2,
            "requested_by": str(uuid4()),
            "usage_reservation_id": reservation_id,
        },
    }
    _Queue.failed = None
    _Queue.last_failed = None
    monkeypatch.setattr(worker, "WorkspaceJobQueue", _Queue)
    monkeypatch.setattr(worker, "SubscriptionStore", lambda _pool: _Subscriptions())

    async def must_not_crawl(*_args, **_kwargs):
        raise AssertionError("crawl must not run after entitlement revocation")

    monkeypatch.setattr(worker, "discover_persisted_workspace_site", must_not_crawl)
    result = asyncio.run(worker.process_one_job(_Pool(), worker_id="worker-test"))

    assert result is True
    assert _Queue.last_failed["error_code"] == "growth_scan_entitlement_denied"
    assert _Queue.last_failed["retry"] is False


class _AllowedSubscriptions:
    async def validate_job_reservation(self, **_kwargs):
        return {"allowed": True, "reason": "allowed", "reservation_status": "consumed"}


class _SuccessfulQueue:
    job = None
    completed = None
    failed = None
    query = None

    def __init__(self, _pool):
        pass

    async def claim(self, **_kwargs):
        return self.job

    async def complete(self, **kwargs):
        type(self).completed = kwargs
        return True

    async def fail(self, **kwargs):
        type(self).failed = kwargs
        return "failed"


class _ReportConnection:
    def __init__(self):
        self.query = None
        self.args = None

    async def fetchrow(self, query, *args):
        from datetime import datetime, timezone
        self.query = query
        self.args = args
        return {"id": uuid4(), "created_at": datetime.now(timezone.utc)}


class _AcquireReportConnection:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class _ReportPool:
    def __init__(self):
        self.connection = _ReportConnection()

    def acquire(self):
        return _AcquireReportConnection(self.connection)


def test_worker_persists_report_idempotently_by_job_id(monkeypatch):
    job_id = str(uuid4())
    reservation_id = str(uuid4())
    _SuccessfulQueue.job = {
        "id": job_id,
        "workspace_id": "trusted-workspace",
        "payload": {
            "start_url": "https://example.com/",
            "business_type": "SaaS",
            "target_market": "US",
            "target_queries": [],
            "max_pages": 2,
            "max_depth": 1,
            "requested_by": str(uuid4()),
            "usage_reservation_id": reservation_id,
        },
    }
    _SuccessfulQueue.completed = None
    _SuccessfulQueue.failed = None
    pool = _ReportPool()
    monkeypatch.setattr(worker, "WorkspaceJobQueue", _SuccessfulQueue)
    monkeypatch.setattr(worker, "SubscriptionStore", lambda _pool: _AllowedSubscriptions())
    monkeypatch.setattr(worker, "DomainAuthorizationStore", lambda _pool: object())

    async def discover(*_args, **_kwargs):
        return {"start_url": "https://example.com/", "crawl_skipped": False, "pages": []}

    monkeypatch.setattr(worker, "discover_persisted_workspace_site", discover)
    result = asyncio.run(worker.process_one_job(pool, worker_id="worker-test"))

    assert result is True
    assert "ON CONFLICT (job_id)" in pool.connection.query
    assert "DO UPDATE SET job_id=EXCLUDED.job_id" in pool.connection.query
    assert pool.connection.args[-1] == job_id
    assert _SuccessfulQueue.completed["result"]["status"] == "completed"
    assert _SuccessfulQueue.failed is None


def test_worker_does_not_retry_deterministically_invalid_payload(monkeypatch):
    _Queue.job = {
        "id": str(uuid4()),
        "workspace_id": "trusted-workspace",
        "payload": {
            "start_url": "https://example.com/",
            "business_type": "SaaS",
            "target_market": "US",
            "target_queries": [],
            "requested_by": "not-a-uuid",
            "max_pages": 10,
            "max_depth": 2,
        },
    }
    _Queue.failed = None
    _Queue.last_failed = None
    monkeypatch.setattr(worker, "WorkspaceJobQueue", _Queue)

    result = asyncio.run(worker.process_one_job(_Pool(), worker_id="worker-test"))

    assert result is True
    assert _Queue.last_failed["error_code"] == "growth_scan_payload_or_domain_rejected"
    assert _Queue.last_failed["retry"] is False
    assert _Queue.last_failed["retry_delay_seconds"] == 0
