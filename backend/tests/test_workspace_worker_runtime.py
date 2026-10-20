import asyncio

from app.services import workspace_worker_runtime as runtime


class Queue:
    def __init__(self, job=None):
        self.job = job
        self.claim_calls = []

    async def claim(self, **kwargs):
        self.claim_calls.append(kwargs)
        return self.job


def test_worker_runtime_returns_idle_when_queue_empty(monkeypatch):
    queue = Queue()

    async def unexpected_process(**kwargs):
        raise AssertionError("must not process a missing job")

    monkeypatch.setattr(runtime, "process_claimed_website_scan", unexpected_process)
    result = asyncio.run(runtime.run_worker_once(
        worker_id="worker-1",
        job_queue=queue,
        domain_store=object(),
        egress_guard=lambda: True,
    ))

    assert result == {"status": "idle"}
    assert queue.claim_calls == [{"worker_id": "worker-1", "lease_seconds": 300}]


def test_worker_runtime_claims_at_most_one_job_and_delegates(monkeypatch):
    job = {"id": "job-1", "job_type": "website_growth_scan", "payload": {}}
    queue = Queue(job)
    store = object()
    guard = lambda: True
    received = {}

    async def fake_process(**kwargs):
        received.update(kwargs)
        return {"status": "failed", "reason": "invalid_scan_job"}

    monkeypatch.setattr(runtime, "process_claimed_website_scan", fake_process)
    result = asyncio.run(runtime.run_worker_once(
        worker_id="worker-2",
        job_queue=queue,
        domain_store=store,
        egress_guard=guard,
        lease_seconds=120,
    ))

    assert result == {"status": "failed", "reason": "invalid_scan_job"}
    assert len(queue.claim_calls) == 1
    assert queue.claim_calls[0] == {"worker_id": "worker-2", "lease_seconds": 120}
    assert received == {
        "job": job,
        "worker_id": "worker-2",
        "domain_store": store,
        "job_queue": queue,
        "egress_guard": guard,
    }
