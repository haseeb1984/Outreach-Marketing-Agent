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
