"""Single-use, short-lived OAuth transaction persistence.

Provider adapters must place the PKCE verifier in an approved secret manager first and
pass only its opaque reference here. This store does not perform OAuth or exchange codes.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.services.provider_oauth_security import validate_redirect_uri
from app.services.secret_manager import InvalidSecretReference, validate_secret_reference

_PKCE_CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_OAUTH_STATE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def new_oauth_state() -> str:
    """Return high-entropy state; persist only its SHA-256 digest."""
    return secrets.token_urlsafe(32)


def digest_oauth_value(value: str) -> str:
    if not isinstance(value, str) or not 32 <= len(value) <= 512:
        raise ValueError("invalid_oauth_value")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class WorkspaceProviderOAuthTransactionStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create(
        self, *, workspace_id: str, connection_id: UUID, user_id: UUID,
        provider: str, state: str, pkce_challenge: str,
        verifier_secret_reference: str, redirect_uri: str, nonce: str,
        allowed_redirect_uris: tuple[str, ...], lifetime_seconds: int = 600,
    ) -> dict[str, Any]:
        if provider not in {"email", "whatsapp"}:
            raise ValueError("invalid_provider")
        if not isinstance(pkce_challenge, str) or not _PKCE_CHALLENGE.fullmatch(pkce_challenge):
            raise ValueError("invalid_pkce_challenge")
        if not isinstance(state, str) or not _OAUTH_STATE.fullmatch(state):
            raise ValueError("invalid_oauth_state")
        if not isinstance(nonce, str) or not _OAUTH_STATE.fullmatch(nonce):
            raise ValueError("invalid_oauth_nonce")
        if not isinstance(allowed_redirect_uris, (tuple, list)) or not allowed_redirect_uris:
            raise ValueError("redirect_uri_allowlist_required")
        try:
            redirect_uri = validate_redirect_uri(redirect_uri, allowed_uris=allowed_redirect_uris)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid_redirect_uri") from exc
        try:
            verifier_secret_reference = validate_secret_reference(verifier_secret_reference)
        except InvalidSecretReference as exc:
            raise ValueError("invalid_verifier_secret_reference") from exc
        if isinstance(lifetime_seconds, bool) or not isinstance(lifetime_seconds, int) or not 60 <= lifetime_seconds <= 900:
            raise ValueError("invalid_oauth_lifetime")
        state_digest = digest_oauth_value(state)
        nonce_digest = digest_oauth_value(nonce)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=lifetime_seconds)
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """INSERT INTO workspace_provider_oauth_transactions
                   (workspace_id, connection_id, user_id, provider, state_sha256,
                    pkce_challenge, verifier_secret_reference, redirect_uri,
                    nonce_sha256, created_at, expires_at)
                   SELECT $1, pc.id, $3, $4, $5, $6, $7, $8, $9, $10, $11
                   FROM workspace_provider_connections pc
                   JOIN workspace_memberships wm
                     ON wm.workspace_id=pc.workspace_id AND wm.user_id=$3
                    AND wm.status='active' AND wm.role IN ('owner','admin')
                   WHERE pc.id=$2 AND pc.workspace_id=$1 AND pc.provider=$4
                     AND pc.status='pending'
                   RETURNING id, workspace_id, connection_id, user_id, provider,
                             pkce_challenge, redirect_uri, created_at, expires_at""",
                workspace_id, connection_id, user_id, provider, state_digest,
                pkce_challenge, verifier_secret_reference.strip(), redirect_uri,
                nonce_digest, now, expires_at,
            )
        if row is None:
            raise ValueError("pending_connection_not_found")
        return self._public(row)

    async def consume(self, *, state: str) -> dict[str, Any] | None:
        """Atomically consume a valid state once; never return raw state or nonce."""
        try:
            state_digest = digest_oauth_value(state)
        except ValueError:
            return None
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """UPDATE workspace_provider_oauth_transactions
                       SET consumed_at=$2
                       WHERE state_sha256=$1 AND consumed_at IS NULL
                         AND expires_at > $2
                       RETURNING id, workspace_id, connection_id, user_id, provider,
                                 pkce_challenge, verifier_secret_reference, redirect_uri,
                                 nonce_sha256, created_at, expires_at, consumed_at""",
                    state_digest, now,
                )
        if row is None:
            return None
        result = self._public(row)
        # Internal-only callback material is explicit and still excludes actual secrets.
        result["verifier_secret_reference"] = row["verifier_secret_reference"]
        result["nonce_sha256"] = row["nonce_sha256"]
        return result

    @staticmethod
    def _public(row: Any) -> dict[str, Any]:
        result = dict(row)
        for key in ("id", "connection_id", "user_id"):
            if result.get(key) is not None:
                result[key] = str(result[key])
        for key in ("created_at", "expires_at", "consumed_at"):
            if result.get(key) is not None:
                result[key] = result[key].isoformat()
        return {key: value for key, value in result.items()
                if key in {"id", "workspace_id", "connection_id", "user_id", "provider",
                           "pkce_challenge", "redirect_uri", "created_at", "expires_at",
                           "consumed_at"}}
