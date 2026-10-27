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
