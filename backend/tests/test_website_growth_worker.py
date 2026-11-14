import asyncio

import pytest

import app.workers.website_growth_worker as worker_module
from app.workers.website_growth_worker import process_claimed_job, validate_scan_payload


def test_worker_payload_accepts_bounded_https_scan():
    payload = validate_scan_payload({
        "start_url": "https://example.com",
        "business_type": "Local services",
        "target_market": "Pakistan",
        "target_queries": ["plumber near me"],
        "max_pages": 5,
        "max_depth": 1,
    })
    assert payload["max_pages"] == 5
    assert payload["target_queries"] == ["plumber near me"]


def test_worker_accepts_and_strips_enqueue_operational_metadata():
    payload = validate_scan_payload({
        "start_url": "https://example.com",
        "business_type": "Retail",
        "target_market": "Pakistan",
        "requested_by": "user-123",
        "usage_reservation_id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
    })
    assert payload["start_url"] == "https://example.com/"
    assert "requested_by" not in payload
    assert "usage_reservation_id" not in payload


def test_worker_strips_query_and_fragment_from_start_url():
    payload = validate_scan_payload({
        "start_url": "https://example.com/path?access_token=secret#section",
        "business_type": "Retail",
        "target_market": "Pakistan",
    })
    assert payload["start_url"] == "https://example.com/path"


@pytest.mark.parametrize("payload", [
    None,
    {"start_url": "http://example.com", "business_type": "x", "target_market": "y"},
    {"start_url": "https://user:pass@example.com", "business_type": "x", "target_market": "y"},
    {"start_url": "https://example.com", "business_type": "x", "target_market": "y", "workspace_id": "forged"},
    {"start_url": "https://example.com", "business_type": "x", "target_market": "y", "max_pages": 11},
    {"start_url": "https://example.com", "business_type": "x", "target_market": "y", "max_depth": 3},
    {"start_url": "https://example.com", "business_type": "x", "target_market": "y", "target_queries": ["q"] * 21},
])
def test_worker_payload_rejects_invalid_or_untrusted_fields(payload):
    with pytest.raises(ValueError):
        validate_scan_payload(payload)


class FakeQueue:
    def __init__(self, complete=True):
        self.complete_result = complete
        self.completed = None
        self.failed = None

    async def extend_lease(self, **kwargs):
        return True

    async def complete(self, **kwargs):
        self.completed = kwargs
        return self.complete_result

    async def fail(self, **kwargs):
        self.failed = kwargs
        return "failed"



class FakeSubscriptions:
    def __init__(self, decision=None):
        self.decision = decision or {"allowed": True, "reason": "allowed"}
        self.calls = []

    async def validate_job_reservation(self, **kwargs):
        self.calls.append(("validate", kwargs))
        return self.decision

    async def check_feature_enabled(self, **kwargs):
        self.calls.append(("check", kwargs))
        return self.decision

    async def finish_reservation(self, **kwargs):
        self.calls.append(("finish", kwargs))
        return True


def test_process_claimed_job_completes_and_uses_database_workspace_identity():
    queue = FakeQueue()
    subscriptions = FakeSubscriptions()
    job = {
        "id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
        "workspace_id": "trusted-db-workspace",
        "payload": {
            "start_url": "https://example.com",
            "business_type": "Retail",
            "target_market": "Pakistan",
            "usage_reservation_id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
        },
    }
    seen = {}

    async def runner(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return {"status": "report_ready_for_human_review", "actions": []}

    outcome = asyncio.run(process_claimed_job(
        queue=queue, domain_store=object(), job=job, worker_id="worker-1", scan_runner=runner,
        subscription_store=subscriptions,
    ))
    assert outcome == "succeeded"
    assert subscriptions.calls[0][0] == "validate"
    assert subscriptions.calls[0][1]["feature"] == "website_audits"
    assert seen["workspace_id"] == "trusted-db-workspace"
    assert seen["max_pages"] == 10
    assert queue.completed["result"]["status"] == "report_ready_for_human_review"


def test_process_claimed_job_returns_lease_lost_if_completion_is_fenced():
    queue = FakeQueue(complete=False)
    subscriptions = FakeSubscriptions()
    job = {
        "id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
        "workspace_id": "trusted-db-workspace",
        "payload": {"start_url": "https://example.com", "business_type": "Retail", "target_market": "Pakistan"},
    }

    async def runner(url, **kwargs):
        return {"status": "report_ready_for_human_review"}

    outcome = asyncio.run(process_claimed_job(
        queue=queue, domain_store=object(), job=job, worker_id="worker-1", scan_runner=runner,
        subscription_store=subscriptions,
    ))
    assert outcome == "lease_lost"


def test_process_claimed_job_records_safe_failure_code():
    queue = FakeQueue()
    subscriptions = FakeSubscriptions()

    async def runner(url, **kwargs):
        raise ValueError("verified_domain_not_authorized")

    outcome = asyncio.run(process_claimed_job(
        queue=queue,
        domain_store=object(),
        job={
            "id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
            "workspace_id": "trusted-db-workspace",
            "payload": {"start_url": "https://example.com", "business_type": "Retail", "target_market": "Pakistan"},
        },
        worker_id="worker-1",
        scan_runner=runner,
        subscription_store=subscriptions,
    ))
    assert outcome == "failed"
    assert queue.failed["error_code"] == "website_scan_rejected"


def test_process_claimed_job_fails_closed_when_quota_reservation_is_invalid():
    queue = FakeQueue()
    subscriptions = FakeSubscriptions({"allowed": False, "reason": "reservation_not_active"})
    called = False

    async def runner(url, **kwargs):
        nonlocal called
        called = True
        return {"status": "report_ready_for_human_review"}

    outcome = asyncio.run(process_claimed_job(
        queue=queue,
        domain_store=object(),
        job={
            "id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
            "workspace_id": "trusted-db-workspace",
            "payload": {
                "start_url": "https://example.com",
                "business_type": "Retail",
                "target_market": "Pakistan",
                "usage_reservation_id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
            },
        },
        worker_id="worker-1",
        scan_runner=runner,
        subscription_store=subscriptions,
    ))
    assert outcome == "failed"
    assert queue.failed["error_code"] == "website_growth_quota_unavailable"
    assert called is False



def test_worker_cancels_scan_when_lease_is_lost(monkeypatch):
    monkeypatch.setattr(worker_module, "HEARTBEAT_SECONDS", 0.01)

    class LostLeaseQueue(FakeQueue):
        async def extend_lease(self, **kwargs):
            return False

    queue = LostLeaseQueue()
    subscriptions = FakeSubscriptions()
    scan_started = asyncio.Event()
    scan_cancelled = asyncio.Event()

    async def runner(url, **kwargs):
        scan_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            scan_cancelled.set()
            raise

    outcome = asyncio.run(process_claimed_job(
        queue=queue,
        domain_store=object(),
        job={
            "id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
            "workspace_id": "trusted-db-workspace",
            "payload": {
                "start_url": "https://example.com",
                "business_type": "Retail",
                "target_market": "Pakistan",
                "usage_reservation_id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
            },
        },
        worker_id="worker-stale",
        scan_runner=runner,
        subscription_store=subscriptions,
    ))

    assert scan_started.is_set()
    assert scan_cancelled.is_set()
    assert outcome == "lease_lost"
    assert queue.completed is None
    assert queue.failed is None


def test_worker_marks_deterministic_payload_rejection_non_retryable():
    queue = FakeQueue()
    subscriptions = FakeSubscriptions()

    outcome = asyncio.run(process_claimed_job(
        queue=queue,
        domain_store=object(),
        job={"id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1", "workspace_id": "workspace-a", "payload": {"start_url": "http://example.com", "business_type": "Retail", "target_market": "Pakistan"}},
        worker_id="worker-1",
        subscription_store=subscriptions,
    ))

    assert outcome == "failed"
    assert queue.failed["error_code"] == "invalid_start_url"
    assert queue.failed["retry"] is False


def test_worker_marks_scan_rejection_non_retryable():
    queue = FakeQueue()
    subscriptions = FakeSubscriptions()

    async def runner(url, **kwargs):
        raise ValueError("verified_domain_not_authorized")

    outcome = asyncio.run(process_claimed_job(
        queue=queue,
        domain_store=object(),
        job={"id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1", "workspace_id": "workspace-a", "payload": {"start_url": "https://example.com", "business_type": "Retail", "target_market": "Pakistan"}},
        worker_id="worker-1",
        scan_runner=runner,
        subscription_store=subscriptions,
    ))

    assert outcome == "failed"
    assert queue.failed["error_code"] == "website_scan_rejected"
    assert queue.failed["retry"] is False



def test_worker_releases_quota_when_production_egress_is_not_configured(monkeypatch):
    queue = FakeQueue()
    subscriptions = FakeSubscriptions()
    monkeypatch.setattr(
        worker_module, "validate_fetch_configuration",
        lambda: (_ for _ in ()).throw(ValueError("proxy missing")),
    )

    outcome = asyncio.run(process_claimed_job(
        queue=queue,
        domain_store=object(),
        job={
            "id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
            "workspace_id": "workspace-a",
            "payload": {
                "start_url": "https://example.com",
                "business_type": "Retail",
                "target_market": "Pakistan",
                "usage_reservation_id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
            },
        },
        worker_id="worker-1",
        subscription_store=subscriptions,
    ))

    assert outcome == "failed"
    assert queue.failed["error_code"] == "website_growth_egress_not_configured"
    assert queue.failed["retry"] is False
    assert ("finish", {
        "workspace_id": "workspace-a",
        "reservation_id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
        "outcome": "released",
    }) in subscriptions.calls
