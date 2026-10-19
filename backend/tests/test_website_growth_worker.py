import asyncio

import pytest

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


def test_process_claimed_job_completes_and_uses_database_workspace_identity():
    queue = FakeQueue()
    job = {
        "id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
        "workspace_id": "trusted-db-workspace",
        "payload": {
            "start_url": "https://example.com",
            "business_type": "Retail",
            "target_market": "Pakistan",
        },
    }
    seen = {}

    async def runner(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return {"status": "report_ready_for_human_review", "actions": []}

    outcome = asyncio.run(process_claimed_job(
        queue=queue, domain_store=object(), job=job, worker_id="worker-1", scan_runner=runner
    ))
    assert outcome == "succeeded"
    assert seen["workspace_id"] == "trusted-db-workspace"
    assert seen["max_pages"] == 10
    assert queue.completed["result"]["status"] == "report_ready_for_human_review"


def test_process_claimed_job_returns_lease_lost_if_completion_is_fenced():
    queue = FakeQueue(complete=False)
    job = {
        "id": "f4c3b4a8-10e0-4a52-9c10-0c7a7ec3b2a1",
        "workspace_id": "trusted-db-workspace",
        "payload": {"start_url": "https://example.com", "business_type": "Retail", "target_market": "Pakistan"},
    }

    async def runner(url, **kwargs):
        return {"status": "report_ready_for_human_review"}

    outcome = asyncio.run(process_claimed_job(
        queue=queue, domain_store=object(), job=job, worker_id="worker-1", scan_runner=runner
    ))
    assert outcome == "lease_lost"


def test_process_claimed_job_records_safe_failure_code():
    queue = FakeQueue()

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
    ))
    assert outcome == "failed"
    assert queue.failed["error_code"] == "website_scan_rejected"
