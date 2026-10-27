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
