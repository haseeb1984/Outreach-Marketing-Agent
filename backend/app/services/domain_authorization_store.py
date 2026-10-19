"""Persistence adapter for workspace domain authorization using PostgreSQL.

The adapter accepts an existing asyncpg-compatible pool/connection; it does not create
connections, run migrations, or derive workspace identity from untrusted request data.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from app.services.domain_authorization import (
    TXT_PREFIX,
    authorize_domain_url,
    issue_dns_challenge,
    normalize_domain,
    verify_dns_challenge,
)


class DomainAuthorizationStore:
    """Transactional domain verification persistence for an asyncpg pool."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def issue_challenge(
        self, *, workspace_id: str, domain: str, now: datetime | None = None
    ) -> dict[str, Any]:
        normalized = normalize_domain(domain)
        issued = issue_dns_challenge(normalized, workspace_id, now=now)
        challenge = issued["challenge"]
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                # Serialize challenges for this workspace/domain so concurrent
                # requests cannot create an unbounded set of live tokens.
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
                    str(workspace_id), normalized,
                )
                await connection.execute(
                    """UPDATE domain_verification_challenges
                       SET status = 'expired'
                       WHERE workspace_id = $1 AND domain_ascii = $2
                         AND status = 'pending' AND expires_at <= $3""",
                    str(workspace_id), normalized,
                    datetime.fromisoformat(challenge["created_at"]),
                )
                await connection.execute(
                    """UPDATE domain_verification_challenges
                       SET status = 'revoked'
                       WHERE workspace_id = $1 AND domain_ascii = $2
                         AND status = 'pending'""",
                    str(workspace_id), normalized,
                )
                await connection.execute(
                    """INSERT INTO domain_verification_challenges
                       (workspace_id, domain_ascii, method, token_sha256, status,
                        created_at, expires_at)
                       VALUES ($1, $2, 'dns_txt', $3, 'pending', $4, $5)""",
                    str(workspace_id), normalized, challenge["token_sha256"],
                    datetime.fromisoformat(challenge["created_at"]),
                    datetime.fromisoformat(challenge["expires_at"]),
                )
        return issued

    async def verify_challenge(
        self,
        *,
        workspace_id: str,
        domain: str,
        txt_values: list[str],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Verify DNS evidence and atomically consume the pending challenge."""
        normalized = normalize_domain(domain)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """SELECT id, workspace_id, domain_ascii, method, token_sha256,
                              status, created_at, expires_at
                       FROM domain_verification_challenges
                       WHERE workspace_id = $1 AND domain_ascii = $2
                         AND status = 'pending'
                       ORDER BY created_at DESC LIMIT 1 FOR UPDATE""",
                    str(workspace_id), normalized,
                )
                if row is None:
                    return {"verified": False, "reason": "pending_challenge_not_found"}
                challenge = dict(row)
                if current.astimezone(timezone.utc) >= challenge["expires_at"].astimezone(timezone.utc):
                    await connection.execute(
                        "UPDATE domain_verification_challenges SET status='expired' WHERE id=$1",
                        challenge["id"],
                    )
                    return {"verified": False, "reason": "challenge_expired"}
                # Validate values using the same constant-time hash comparison as the
                # pure helper. The database row is locked while this result is consumed.
                result = verify_dns_challenge(
                    {
                        "workspace_id": challenge["workspace_id"],
                        "domain": challenge["domain_ascii"],
                        "method": challenge["method"],
                        "token_sha256": challenge["token_sha256"],
                        "status": challenge["status"],
                        "expires_at": challenge["expires_at"].isoformat(),
                    },
                    txt_values,
                    now=current,
                )
                if not result["verified"]:
                    return result
                await connection.execute(
                    """UPDATE domain_verification_challenges
                       SET status='verified', verified_at=$2 WHERE id=$1 AND status='pending'""",
                    challenge["id"], current.astimezone(timezone.utc),
                )
                await connection.execute(
                    """INSERT INTO workspace_domains
                       (workspace_id, domain_ascii, status, verification_method,
                        verified_at, revoked_at, updated_at)
                       VALUES ($1, $2, 'verified', 'dns_txt', $3, NULL, $3)
                       ON CONFLICT (workspace_id, domain_ascii) DO UPDATE SET
                         status='verified', verification_method='dns_txt',
                         verified_at=EXCLUDED.verified_at, revoked_at=NULL,
                         updated_at=EXCLUDED.updated_at""",
                    str(workspace_id), normalized, current.astimezone(timezone.utc),
                )
                return result

    async def get_verified_domains(self, *, workspace_id: str) -> list[dict[str, Any]]:
        """Load active domain records only for an authenticated workspace ID."""
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                """SELECT workspace_id, domain_ascii AS domain, status, verified_at,
                          revoked_at
                   FROM workspace_domains
                   WHERE workspace_id=$1 AND status='verified' AND revoked_at IS NULL
                   ORDER BY domain_ascii""",
                str(workspace_id),
            )
        return [dict(row) for row in rows]

    async def authorize_url(self, *, workspace_id: str, url: str) -> dict[str, str]:
        """Authorize using persisted records; caller must supply trusted identity."""
        records = await self.get_verified_domains(workspace_id=workspace_id)
        return authorize_domain_url(url, workspace_id, records)

    async def revoke_domain(self, *, workspace_id: str, domain: str) -> bool:
        normalized = normalize_domain(domain)
        current = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """UPDATE workspace_domains
                       SET status='revoked', revoked_at=$3, updated_at=$3
                       WHERE workspace_id=$1 AND domain_ascii=$2
                         AND status='verified' AND revoked_at IS NULL""",
                    str(workspace_id), normalized, current,
                )
                await connection.execute(
                    """UPDATE domain_verification_challenges SET status='revoked'
                       WHERE workspace_id=$1 AND domain_ascii=$2 AND status='pending'""",
                    str(workspace_id), normalized,
                )
        return result.endswith(" 1")

    async def get_pending_challenge(
        self, *, workspace_id: str, domain: str
    ) -> dict[str, Any] | None:
        """Return minimal challenge metadata before DNS resolution, not its token hash."""
        normalized = normalize_domain(domain)
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT workspace_id, domain_ascii AS domain, status, expires_at
                   FROM domain_verification_challenges
                   WHERE workspace_id=$1 AND domain_ascii=$2 AND status='pending'
                   ORDER BY created_at DESC LIMIT 1""",
                str(workspace_id), normalized,
            )
        return dict(row) if row is not None else None

