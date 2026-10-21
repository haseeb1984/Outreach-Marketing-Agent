import asyncio

import pytest

from app.services import workspace_scan_worker as worker


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


class Queue:
    def __init__(self):
        self.failures = []
        self.completions = []

    async def fail(self, **kwargs):
        self.failures.append(kwargs)
        return "failed"

    async def complete(self, **kwargs):
        self.completions.append(kwargs)
        return True


def job(**overrides):
    result = {
        "id": "job-1",
        "workspace_id": "ws-1",
        "job_type": "website_growth_scan",
        "payload": {
            "start_url": "https://client.example/",
            "authorized_domain": "client.example",
            "max_pages": 10,
            "max_depth": 1,
        },
    }
    result.update(overrides)
    return result


def test_worker_rechecks_authorization_and_fails_closed_without_egress_guard(monkeypatch):
    store = Store({
        "workspace_id": "ws-1",
        "url": "https://client.example/",
        "host": "client.example",
    })
    queue = Queue()
    called = False

    async def unexpected_discovery(**kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(worker, "discover_authorized_website", unexpected_discovery)
    result = asyncio.run(worker.process_claimed_website_scan(
        job=job(),
        worker_id="worker-1",
        domain_store=store,
        job_queue=queue,
    ))

    assert result == {"status": "failed", "reason": "egress_policy_unavailable"}
    assert len(store.calls) == 1
    assert called is False
    assert queue.failures[0]["error_code"] == "egress_policy_unavailable"
    assert queue.completions == []


def test_worker_rejects_domain_revoked_after_enqueue(monkeypatch):
    store = Store(error=PermissionError("domain revoked"))
    queue = Queue()

    async def unexpected_discovery(**kwargs):
        pytest.fail("network discovery must not run after authorization failure")

    monkeypatch.setattr(worker, "discover_authorized_website", unexpected_discovery)
    result = asyncio.run(worker.process_claimed_website_scan(
        job=job(),
        worker_id="worker-1",
        domain_store=store,
        job_queue=queue,
        egress_guard=lambda: True,
    ))

    assert result == {"status": "failed", "reason": "domain_authorization_failed"}
    assert queue.failures[0]["error_code"] == "domain_authorization_failed"
    assert queue.completions == []


def test_worker_rejects_authorized_host_mismatch_before_egress_check(monkeypatch):
    store = Store({
        "workspace_id": "ws-1",
        "url": "https://other.example/",
        "host": "other.example",
    })
    queue = Queue()
    guard_calls = []

    async def unexpected_discovery(**kwargs):
        pytest.fail("network discovery must not run for a host mismatch")

    monkeypatch.setattr(worker, "discover_authorized_website", unexpected_discovery)
    result = asyncio.run(worker.process_claimed_website_scan(
        job=job(),
        worker_id="worker-1",
        domain_store=store,
        job_queue=queue,
        egress_guard=lambda: guard_calls.append(True) or True,
    ))

    assert result["reason"] == "domain_authorization_failed"
    assert guard_calls == []
    assert queue.completions == []


def test_worker_completes_with_compact_summary_only_after_guard_and_auth(monkeypatch):
    store = Store({
        "workspace_id": "ws-1",
        "url": "https://client.example/",
        "host": "client.example",
    })
    queue = Queue()

    async def fake_discovery(**kwargs):
        assert kwargs["workspace_id"] == "ws-1"
        assert kwargs["start_url"] == "https://client.example/"
        return {
            "authorized_domain": "client.example",
            "discovery": {
                "start_url": "https://client.example/",
                "crawl_skipped": False,
                "crawl": {
                    "pages_crawled": 2,
                    "aggregate_findings": [{
                        "code": "missing_description",
                        "title": "Missing description",
                        "severity": "low",
                        "occurrences": 2,
                        "evidence_urls": ["https://client.example/"],
                    }],
                    "errors": [],
                    "robots_blocked_pages": [],
                    "cross_host_redirects_not_crawled": [],
                },
            },
        }

    monkeypatch.setattr(worker, "discover_authorized_website", fake_discovery)
    result = asyncio.run(worker.process_claimed_website_scan(
        job=job(),
        worker_id="worker-1",
        domain_store=store,
        job_queue=queue,
        egress_guard=lambda: True,
    ))

    assert result == {"status": "succeeded", "job_id": "job-1"}
    assert queue.failures == []
    assert len(queue.completions) == 1
    persisted = queue.completions[0]["result"]
    assert persisted["pages_crawled"] == 2
    assert persisted["aggregate_findings"][0]["code"] == "missing_description"
    assert "pages" not in persisted
    assert "raw_html" not in persisted


def test_worker_fails_closed_if_egress_guard_raises(monkeypatch):
    store = Store({
        "workspace_id": "ws-1",
        "url": "https://client.example/",
        "host": "client.example",
    })
    queue = Queue()

    async def unexpected_discovery(**kwargs):
        pytest.fail("no target request allowed when guard fails")

    async def broken_guard():
        raise RuntimeError("private config detail")

    monkeypatch.setattr(worker, "discover_authorized_website", unexpected_discovery)
    result = asyncio.run(worker.process_claimed_website_scan(
        job=job(),
        worker_id="worker-1",
        domain_store=store,
        job_queue=queue,
        egress_guard=broken_guard,
    ))

    assert result["reason"] == "egress_policy_unavailable"
    assert queue.failures[0]["error_code"] == "egress_policy_unavailable"



def test_compact_report_omits_cross_host_and_secret_bearing_evidence_urls():
    compact = worker._compact_report({
        "authorized_domain": "client.example",
        "discovery": {
            "start_url": "https://client.example/",
            "crawl": {
                "pages_crawled": "3",
                "aggregate_findings": [{
                    "code": "title",
                    "title": "Title finding",
                    "occurrences": "not-a-number",
                    "evidence_urls": [
                        "https://client.example/products",
                        "https://client.example/products?token=secret",
                        "https://client.example/products#private",
                        "https://user:secret@client.example/account",
                        "https://attacker.example/collect",
                        "javascript:alert(1)",
                    ],
                }, None, "malformed"],
                "errors": [],
            },
        },
    })

    assert compact["pages_crawled"] == 3
    assert compact["finding_types_total"] == 3
    assert compact["aggregate_findings"][0]["occurrences"] == 0
    assert compact["aggregate_findings"][0]["evidence_urls"] == [
        "https://client.example/products"
    ]
    assert "secret" not in str(compact)


@pytest.mark.parametrize("bad_crawl", [None, "unexpected", 123])
def test_compact_report_handles_malformed_crawl_payload_without_crashing(bad_crawl):
    compact = worker._compact_report({
        "authorized_domain": "client.example",
        "discovery": {"crawl": bad_crawl},
    })
    assert compact["pages_crawled"] == 0
    assert compact["aggregate_findings"] == []
    assert compact["errors_count"] == 0
