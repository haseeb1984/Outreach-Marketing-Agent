"""DNS-backed domain verification orchestration.

DNS evidence is fetched by the server, never accepted from an HTTP request body.
The store rechecks challenge status/expiry under a database lock before consuming it.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import dns.asyncresolver
import dns.exception
import dns.resolver

from app.services.domain_authorization import normalize_domain

TxtLookup = Callable[[str], Awaitable[list[str]]]


async def lookup_dns_txt(record_name: str, *, timeout_seconds: float = 3.0) -> list[str]:
    """Resolve TXT records with a strict timeout; concatenate split TXT chunks."""
    if not 0 < timeout_seconds <= 5:
        raise ValueError("DNS timeout must be greater than zero and at most 5 seconds")
    resolver = dns.asyncresolver.Resolver(configure=True)
    resolver.timeout = timeout_seconds
    resolver.lifetime = timeout_seconds
    try:
        answer = await resolver.resolve(record_name, "TXT", lifetime=timeout_seconds)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        return []
    except (dns.exception.Timeout, dns.resolver.LifetimeTimeout):
        return []
    values: list[str] = []
    for record in answer:
        # dnspython represents a single TXT record as one or more byte-string
        # chunks; DNS clients must concatenate chunks belonging to that record.
        values.append(b"".join(record.strings).decode("utf-8", errors="replace"))
    return values


class DomainVerificationService:
    """Coordinates server-side DNS lookup and transactional challenge consumption."""

    def __init__(self, store: Any, *, txt_lookup: TxtLookup = lookup_dns_txt) -> None:
        self._store = store
        self._txt_lookup = txt_lookup

    async def verify_domain(self, *, workspace_id: str, domain: str) -> dict[str, Any]:
        normalized = normalize_domain(domain)
        challenge = await self._store.get_pending_challenge(
            workspace_id=workspace_id, domain=normalized
        )
        if challenge is None:
            return {"verified": False, "reason": "pending_challenge_not_found"}
        record_name = f"_oma-verify.{normalized}"
        try:
            values = await asyncio.wait_for(self._txt_lookup(record_name), timeout=5.5)
        except (TimeoutError, OSError, ValueError):
            return {"verified": False, "reason": "dns_lookup_failed"}
        # verify_challenge re-reads and locks the persisted challenge, so a challenge
        # revoked/replaced during DNS resolution cannot be consumed from stale state.
        return await self._store.verify_challenge(
            workspace_id=workspace_id,
            domain=normalized,
            txt_values=values,
        )
