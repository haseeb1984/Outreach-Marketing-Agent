"""Domain-ownership challenge and workspace-scope authorization primitives.

These pure helpers do not perform DNS lookups or persist state. Production callers
must persist challenges and domain records transactionally, resolve DNS through a
trusted resolver, and authorize the authenticated workspace on every request.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from app.services.website_audit import validate_page_url

TXT_PREFIX = "outreach-marketing-agent-verification="


def normalize_domain(value: str) -> str:
    """Normalize a DNS hostname; reject URL syntax, IP literals, and local names."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A domain name is required")
    candidate = value.strip().rstrip(".").lower()
    if "://" in candidate or "/" in candidate or "@" in candidate or ":" in candidate:
        raise ValueError("Provide a hostname only, without scheme, path, port, or credentials")
    try:
        candidate = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Domain name is invalid") from exc
    if len(candidate) > 253 or not candidate or "." not in candidate:
        raise ValueError("A fully qualified domain name is required")
    labels = candidate.split(".")
    if any(
        not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
        or any(not (ch.isalnum() or ch == "-") for ch in label)
        for label in labels
    ):
        raise ValueError("Domain name contains an invalid DNS label")
    if candidate == "localhost" or candidate.endswith(".localhost"):
        raise ValueError("Localhost cannot be verified as a public client domain")
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        pass
    else:
        raise ValueError("IP addresses are not accepted as ownership domains")
    return candidate


def issue_dns_challenge(
    domain: str,
    workspace_id: str,
    *,
    now: datetime | None = None,
    ttl: timedelta = timedelta(hours=24),
) -> dict[str, Any]:
    """Create a short-lived DNS TXT challenge; persist returned metadata securely."""
    normalized = normalize_domain(domain)
    workspace = str(workspace_id).strip()
    if not workspace or len(workspace) > 200:
        raise ValueError("A valid workspace identifier is required")
    if ttl <= timedelta(0) or ttl > timedelta(days=7):
        raise ValueError("Challenge TTL must be greater than zero and no more than 7 days")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    token = secrets.token_urlsafe(32)
    return {
        "workspace_id": workspace,
        "domain": normalized,
        "method": "dns_txt",
        "record_name": f"_oma-verify.{normalized}",
        "record_value": TXT_PREFIX + token,
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "status": "pending",
        "created_at": current.astimezone(timezone.utc).isoformat(),
        "expires_at": (current + ttl).astimezone(timezone.utc).isoformat(),
    }


def verify_dns_challenge(
    challenge: dict[str, Any],
    txt_values: list[str],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify observed TXT values against a persisted, unexpired challenge record."""
    if not isinstance(challenge, dict) or challenge.get("method") != "dns_txt":
        raise ValueError("A DNS TXT challenge record is required")
    if challenge.get("status") != "pending":
        return {"verified": False, "reason": "challenge_not_pending"}
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    try:
        expiry = datetime.fromisoformat(str(challenge["expires_at"]))
        expected_hash = str(challenge["token_sha256"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Challenge record is incomplete or invalid") from exc
    if expiry.tzinfo is None or current.astimezone(timezone.utc) >= expiry.astimezone(timezone.utc):
        return {"verified": False, "reason": "challenge_expired"}
    if not isinstance(txt_values, list):
        raise ValueError("txt_values must be a list of DNS TXT strings")
    found = False
    for value in txt_values:
        if not isinstance(value, str) or not value.startswith(TXT_PREFIX):
            continue
        token = value[len(TXT_PREFIX):]
        actual_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if hmac.compare_digest(actual_hash, expected_hash):
            found = True
            break
    return {
        "verified": found,
        "reason": "dns_txt_token_matched" if found else "dns_txt_token_not_found",
        "domain": challenge.get("domain"),
        "workspace_id": challenge.get("workspace_id"),
    }


def authorize_domain_url(
    url: str,
    workspace_id: str,
    verified_domains: list[dict[str, Any]],
) -> dict[str, str]:
    """Authorize exact-host URLs only for a matching verified workspace record.

    Subdomains are deliberately not implied: verify each host separately unless a
    future, explicitly designed wildcard verification flow is introduced.
    """
    normalized_url = validate_page_url(url)
    parsed = urlsplit(normalized_url)
    host = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
    workspace = str(workspace_id).strip()
    if not workspace:
        raise ValueError("An authenticated workspace identifier is required")
    if not isinstance(verified_domains, list):
        raise ValueError("verified_domains must be a list")
    for record in verified_domains:
        if not isinstance(record, dict):
            continue
        try:
            record_domain = normalize_domain(str(record.get("domain", "")))
        except ValueError:
            continue
        if (
            record.get("workspace_id") == workspace
            and record_domain == host
            and record.get("status") == "verified"
            and not record.get("revoked_at")
        ):
            return {"url": normalized_url, "host": host, "workspace_id": workspace}
    raise PermissionError("This workspace has no active verified authorization for the target domain")
