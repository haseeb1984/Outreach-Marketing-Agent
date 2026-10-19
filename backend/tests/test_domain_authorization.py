from datetime import datetime, timedelta, timezone

import pytest

from app.services.domain_authorization import (
    authorize_domain_url,
    issue_dns_challenge,
    normalize_domain,
    verify_dns_challenge,
)


def test_normalize_domain_accepts_idn_and_rejects_url_or_ip():
    assert normalize_domain("WWW.Example.COM.") == "www.example.com"
    assert normalize_domain("münich.example") == "xn--mnich-kva.example"
    for invalid in ("https://example.com", "example.com/path", "127.0.0.1", "localhost", "bad..example"):
        with pytest.raises(ValueError):
            normalize_domain(invalid)


def test_dns_challenge_verifies_only_matching_token_before_expiry():
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    issued = issue_dns_challenge("Example.com", "workspace-1", now=now)
    challenge = issued["challenge"]
    record = issued["dns_record"]
    assert record["record_name"] == "_oma-verify.example.com"
    assert "token_sha256" in challenge
    assert record["record_value"].startswith("outreach-marketing-agent-verification=")
    assert challenge["token_sha256"] not in record["record_value"]
    assert "record_value" not in challenge
    assert verify_dns_challenge(challenge, ["unrelated=value"], now=now)["verified"] is False
    assert verify_dns_challenge(challenge, [record["record_value"]], now=now)["verified"] is True
    assert verify_dns_challenge(
        challenge, [record["record_value"]], now=now + timedelta(days=2)
    )["reason"] == "challenge_expired"


def test_dns_challenge_requires_pending_record_and_timezone_aware_time():
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    issued = issue_dns_challenge("example.com", "workspace-1", now=now)
    challenge = issued["challenge"]
    challenge["status"] = "verified"
    assert verify_dns_challenge(challenge, [issued["dns_record"]["record_value"]], now=now)["reason"] == "challenge_not_pending"
    with pytest.raises(ValueError):
        issue_dns_challenge("example.com", "workspace-1", now=datetime(2026, 10, 20))


def test_authorization_requires_exact_domain_workspace_and_active_verified_status():
    records = [
        {"domain": "example.com", "workspace_id": "workspace-1", "status": "verified"},
    ]
    assert authorize_domain_url("https://example.com/path", "workspace-1", records)["host"] == "example.com"
    for url, workspace, rows in (
        ("https://sub.example.com/", "workspace-1", records),
        ("https://example.com/", "workspace-2", records),
        ("https://example.com/", "workspace-1", [{**records[0], "status": "pending"}]),
        ("https://example.com/", "workspace-1", [{**records[0], "revoked_at": "2026-10-20T00:00:00+00:00"}]),
    ):
        with pytest.raises(PermissionError):
            authorize_domain_url(url, workspace, rows)
