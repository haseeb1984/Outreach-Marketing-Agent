"""PostgreSQL-backed rate limiting with keyed, non-reversible identifiers.

This primitive is for future auth routes, not middleware by itself. Call it before
password hashing, token delivery, or other expensive/sensitive authentication work.
Never log identifiers, key digests, secrets, or raw database exceptions.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any


class RateLimitConfigurationError(ValueError):
    """Raised when the application secret is too weak for keyed identifiers."""


class AuthRateLimiter:
    def __init__(self, pool: Any, *, secret_key: str) -> None:
        if not isinstance(secret_key, str) or len(secret_key.encode("utf-8")) < 32:
            raise RateLimitConfigurationError("rate_limit_secret_must_be_at_least_32_bytes")
        self._pool = pool
        self._key = secret_key.encode("utf-8")

    def _digest(self, *, namespace: str, identifier: str) -> str:
        if not isinstance(namespace, str) or not namespace or len(namespace) > 80:
            raise ValueError("invalid_rate_limit_namespace")
        if not isinstance(identifier, str) or not identifier or len(identifier) > 2048:
            raise ValueError("invalid_rate_limit_identifier")
        message = (namespace + chr(0) + identifier.strip().lower()).encode("utf-8")
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    async def consume(self, *, namespace: str, identifier: str, limit: int, window_seconds: int) -> dict[str, Any]:
        """Atomically consume an attempt and return allowed, remaining, and reset_at.

        Use separate namespaces for controls such as login email and registration IP.
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100_000:
            raise ValueError("invalid_rate_limit")
        if isinstance(window_seconds, bool) or not isinstance(window_seconds, int) or not 1 <= window_seconds <= 31_536_000:
            raise ValueError("invalid_rate_limit_window")
        digest = self._digest(namespace=namespace, identifier=identifier)
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """INSERT INTO auth_rate_limit_buckets
                     (key_digest, window_started_at, attempts, updated_at)
                   VALUES ($1, $2, 1, $2)
                   ON CONFLICT (key_digest) DO UPDATE SET
                     window_started_at = CASE
                       WHEN auth_rate_limit_buckets.window_started_at + make_interval(secs => $3) <= $2
                       THEN $2 ELSE auth_rate_limit_buckets.window_started_at END,
                     attempts = CASE
                       WHEN auth_rate_limit_buckets.window_started_at + make_interval(secs => $3) <= $2
                       THEN 1 ELSE auth_rate_limit_buckets.attempts + 1 END,
                     updated_at = GREATEST(
                       auth_rate_limit_buckets.updated_at,
                       $2,
                       CASE
                         WHEN auth_rate_limit_buckets.window_started_at + make_interval(secs => $3) <= $2
                         THEN $2 ELSE auth_rate_limit_buckets.window_started_at
                       END
                     )
                   RETURNING attempts, window_started_at""",
                digest, now, window_seconds,
            )
        attempts = int(row["attempts"])
        started = row["window_started_at"]
        return {
            "allowed": attempts <= limit,
            "remaining": max(0, limit - attempts),
            "reset_at": started + timedelta(seconds=window_seconds),
        }
