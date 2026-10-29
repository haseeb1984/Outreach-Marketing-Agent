import asyncio

import pytest

from app.services.workspace_job_queue import (
    MAX_PAYLOAD_BYTES,
    validate_job_request,
)


def test_job_validation_accepts_only_known_type_and_json_payload():
    encoded = validate_job_request(
        job_type="website_growth_scan",
        payload={"url": "https://client.example", "max_pages": 10},
        idempotency_key="scan-2026-10-20",
    )
    assert '"max_pages":10' in encoded


def test_job_validation_rejects_unknown_job_type():
    with pytest.raises(ValueError, match="Unsupported job type"):
        validate_job_request(
            job_type="send_mass_email", payload={}, idempotency_key=None
        )


def test_job_validation_rejects_non_json_payload():
    with pytest.raises(ValueError, match="valid JSON"):
        validate_job_request(
            job_type="website_growth_scan",
            payload={"not_json": object()},
            idempotency_key=None,
        )


def test_job_validation_rejects_oversized_payload():
    with pytest.raises(ValueError, match="64 KiB"):
        validate_job_request(
            job_type="website_growth_scan",
            payload={"blob": "x" * MAX_PAYLOAD_BYTES},
            idempotency_key=None,
        )


def test_job_validation_rejects_blank_idempotency_key():
    with pytest.raises(ValueError, match="Idempotency key"):
        validate_job_request(
            job_type="website_growth_scan", payload={}, idempotency_key="  "
        )


from scripts.run_workspace_growth_worker import _bounded_payload


def test_growth_worker_payload_requires_requester_and_bounded_scan_limits():
    payload = _bounded_payload({
        "start_url": "https://example.com",
        "business_type": "SaaS",
        "target_market": "United States",
        "target_queries": [" crm ", "crm"],
        "requested_by": "d7a2c19a-1b18-42e6-8ed0-67e2b16d7a2a",
        "max_pages": 10,
        "max_depth": 2,
    })
    assert payload["target_queries"] == ["crm"]
    assert payload["max_pages"] == 10


@pytest.mark.parametrize("bad", [
    {},
    {"start_url": "https://example.com", "business_type": "SaaS", "target_market": "US", "requested_by": "user", "target_queries": [], "max_pages": 11, "max_depth": 2},
    {"start_url": "https://example.com", "business_type": "SaaS", "target_market": "US", "requested_by": "user", "target_queries": ["x" * 201], "max_pages": 1, "max_depth": 0},
])
def test_growth_worker_rejects_invalid_payloads(bad):
    with pytest.raises(ValueError, match="job_payload_invalid"):
        _bounded_payload(bad)


def test_growth_worker_rejects_non_uuid_requester():
    with pytest.raises(ValueError, match="job_payload_invalid"):
        _bounded_payload({
            "start_url": "https://example.com",
            "business_type": "SaaS",
            "target_market": "United States",
            "target_queries": [],
            "requested_by": "not-a-uuid",
            "max_pages": 10,
            "max_depth": 2,
        })


from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from app.services.workspace_job_queue import WorkspaceJobQueue


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _IdempotencyConnection:
    def __init__(self, existing_payload):
        self.existing_payload = existing_payload
        self.inserted_payload = None

    def transaction(self):
        return _FakeTransaction()

    async def fetchrow(self, query, *args):
        if "INSERT INTO workspace_jobs" in query:
            self.inserted_payload = args[2]
            return None
        if "SELECT id, workspace_id, job_type, status, payload" in query:
            return {
                "id": uuid4(),
                "workspace_id": args[0],
                "job_type": args[1],
                "status": "queued",
                "payload": self.existing_payload,
                "attempt_count": 0,
                "max_attempts": 3,
                "run_after": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc),
            }
        raise AssertionError(f"Unexpected SQL in queue test: {query}")


class _AcquireConnection:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class _FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _AcquireConnection(self.connection)


def test_enqueue_idempotency_replay_returns_existing_job_when_payload_matches():
    payload = {"start_url": "https://example.com/", "max_pages": 5}
    connection = _IdempotencyConnection(existing_payload=payload)
    queue = WorkspaceJobQueue(_FakePool(connection))

    result = asyncio.run(queue.enqueue(
        workspace_id="workspace-a",
        job_type="website_growth_scan",
        payload=payload,
        idempotency_key="same-request-key",
    ))

    assert result["payload"] == payload
    assert result["status"] == "queued"
    assert connection.inserted_payload == '{"start_url":"https://example.com/","max_pages":5}'


def test_enqueue_rejects_idempotency_key_reused_with_different_payload():
    connection = _IdempotencyConnection(existing_payload={
        "start_url": "https://example.com/original",
        "max_pages": 5,
    })
    queue = WorkspaceJobQueue(_FakePool(connection))

    with pytest.raises(ValueError, match="idempotency_key_conflict"):
        asyncio.run(queue.enqueue(
            workspace_id="workspace-a",
            job_type="website_growth_scan",
            payload={"start_url": "https://example.com/changed", "max_pages": 5},
            idempotency_key="same-request-key",
        ))


class _CancelConnection:
    def __init__(self, payload):
        self.payload = payload
        self.queries = []
        self.transaction_count = 0

    def transaction(self):
        self.transaction_count += 1
        return _FakeTransaction()

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        if "SELECT payload FROM workspace_jobs" in query:
            return {"payload": self.payload}
        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query, *args):
        self.queries.append((query, args))
        if "UPDATE workspace_jobs" in query:
            return "UPDATE 1"
        if "UPDATE feature_usage_reservations" in query:
            return "UPDATE 1"
        raise AssertionError(f"Unexpected query: {query}")


def test_cancel_queued_job_releases_its_quota_reservation_in_same_transaction():
    from uuid import uuid4
    reservation_id = str(uuid4())
    connection = _CancelConnection({"usage_reservation_id": reservation_id})
    queue = WorkspaceJobQueue(_FakePool(connection))

    result = asyncio.run(queue.cancel(
        workspace_id="workspace-a", job_id=uuid4()
    ))

    assert result is True
    assert connection.transaction_count == 1
    assert any("FOR UPDATE" in query for query, _ in connection.queries)
    assert any("status IN ('reserved','consumed')" in query for query, _ in connection.queries)


class _TerminalFailureConnection:
    def __init__(self, reservation_id):
        self.reservation_id = reservation_id
        self.queries = []

    def transaction(self):
        return _FakeTransaction()

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        if "SELECT attempt_count, max_attempts, workspace_id, payload" in query:
            return {
                "attempt_count": 3,
                "max_attempts": 3,
                "workspace_id": "workspace-a",
                "payload": {"usage_reservation_id": self.reservation_id},
            }
        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query, *args):
        self.queries.append((query, args))
        if "UPDATE workspace_jobs SET status='failed'" in query:
            return "UPDATE 1"
        if "UPDATE feature_usage_reservations" in query:
            return "UPDATE 1"
        raise AssertionError(f"Unexpected query: {query}")


def test_terminal_job_failure_releases_consumed_quota_reservation():
    reservation_id = str(uuid4())
    connection = _TerminalFailureConnection(reservation_id)
    queue = WorkspaceJobQueue(_FakePool(connection))

    result = asyncio.run(queue.fail(
        job_id=uuid4(),
        worker_id="worker-test",
        error_code="growth_scan_failed",
        retry=True,
    ))

    assert result == "failed"
    assert any("UPDATE feature_usage_reservations" in query for query, _ in connection.queries)
    release_query, release_args = next(
        (query, args) for query, args in connection.queries
        if "UPDATE feature_usage_reservations" in query
    )
    assert "status IN ('reserved','consumed')" in release_query
    assert str(release_args[0]) == reservation_id
    assert release_args[1] == "workspace-a"
