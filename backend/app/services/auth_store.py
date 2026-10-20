"""PostgreSQL persistence for revocable sessions and workspace membership checks.

This adapter does not expose HTTP routes. Only call it with a server-side database pool;
never accept user_id or workspace_id as proof of identity from a request body.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from app.services.auth_security import new_opaque_token, token_digest

ALLOWED_ROLES = {"owner", "admin", "member", "viewer"}
ROLE_RANK = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}


class AuthStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def register_user(
        self, *, email: str, password: str, verification_lifetime_hours: int = 24,
    ) -> dict[str, Any] | None:
        """Create a pending user, personal workspace, owner membership and verification token.

        Returns the raw verification token once for a trusted email-delivery adapter.
        A duplicate email returns None so an eventual public route can use a generic
        response and avoid revealing whether an account exists. No email is sent here.
        """
        from app.services.auth_security import hash_password, normalize_email

        normalized_email = normalize_email(email)
        password_hash = hash_password(password).encoded
        if (
            isinstance(verification_lifetime_hours, bool)
            or not isinstance(verification_lifetime_hours, int)
            or not 1 <= verification_lifetime_hours <= 72
        ):
            raise ValueError("verification_lifetime_out_of_range")
        token = new_opaque_token()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=verification_lifetime_hours)
        workspace_id = str(uuid4())
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                user = await connection.fetchrow(
                    """INSERT INTO app_users (email, password_hash, status)
                       VALUES ($1, $2, 'pending_verification')
                       ON CONFLICT (email) DO NOTHING
                       RETURNING id, email, status, created_at""",
                    normalized_email, password_hash,
                )
                if user is None:
                    return None
                await connection.execute(
                    "INSERT INTO workspaces (id) VALUES ($1)", workspace_id
                )
                await connection.execute(
                    """INSERT INTO workspace_memberships
                       (workspace_id, user_id, role, status)
                       VALUES ($1, $2, 'owner', 'active')""",
                    workspace_id, user["id"],
                )
                await connection.execute(
                    """INSERT INTO email_verification_tokens
                       (user_id, token_sha256, created_at, expires_at)
                       VALUES ($1, $2, $3, $4)""",
                    user["id"], token_digest(token), now, expires_at,
                )
                await connection.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id, actor_user_id, event_type, outcome, metadata, created_at)
                       VALUES ($1, $2, 'registration.created', 'success', '{}'::jsonb, $3)""",
                    workspace_id, user["id"], now,
                )
        return {
            "user_id": str(user["id"]),
            "email": normalized_email,
            "workspace_id": workspace_id,
            "verification_token": token,
            "verification_expires_at": expires_at,
        }

    async def verify_email(self, token: str) -> bool:
        """Atomically consume a live verification token and activate its user."""
        try:
            digest = token_digest(token)
        except ValueError:
            return False
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """SELECT id, user_id FROM email_verification_tokens
                       WHERE token_sha256=$1 AND consumed_at IS NULL
                         AND expires_at > $2 FOR UPDATE""",
                    digest, now,
                )
                if row is None:
                    return False
                updated = await connection.fetchrow(
                    """UPDATE app_users SET email_verified_at=$2, status='active',
                              updated_at=$2
                       WHERE id=$1 AND status='pending_verification'
                         AND email_verified_at IS NULL
                       RETURNING id""",
                    row["user_id"], now,
                )
                if updated is None:
                    # Do not allow a token to reactivate suspended/deleted users.
                    await connection.execute(
                        "UPDATE email_verification_tokens SET consumed_at=$2 WHERE id=$1",
                        row["id"], now,
                    )
                    return False
                await connection.execute(
                    "UPDATE email_verification_tokens SET consumed_at=$2 WHERE id=$1",
                    row["id"], now,
                )
                await connection.execute(
                    """UPDATE email_verification_tokens SET consumed_at=$2
                       WHERE user_id=$1 AND consumed_at IS NULL AND id<>$3""",
                    row["user_id"], now, row["id"],
                )
                return True

    async def authenticate_password(self, *, email: str, password: str) -> dict[str, str] | None:
        """Verify credentials without revealing account state or returning password hashes.

        Only active, email-verified accounts can authenticate. Invalid emails, wrong
        passwords, pending accounts, suspended accounts, and missing accounts all
        return None so an HTTP layer can expose one generic failure response.
        Rate limiting must be applied by the HTTP layer before calling this method.
        """
        from app.services.auth_security import normalize_email, verify_password

        try:
            normalized_email = normalize_email(email)
        except ValueError:
            return None
        if not isinstance(password, str) or len(password) > 1024:
            return None
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT id, email, password_hash FROM app_users
                   WHERE email=$1 AND status='active'
                     AND email_verified_at IS NOT NULL""",
                normalized_email,
            )
        # Do not perform a password-hash check when there is no eligible account.
        # Public routes must still rate-limit and use a generic response.
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        return {"user_id": str(row["id"]), "email": row["email"]}

    async def create_session(
        self, *, user_id: UUID | str, user_agent: str | None = None,
        lifetime_hours: int = 24,
    ) -> dict[str, Any]:
        if isinstance(lifetime_hours, bool) or not isinstance(lifetime_hours, int) or not 1 <= lifetime_hours <= 720:
            raise ValueError("session_lifetime_out_of_range")
        token = new_opaque_token()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=lifetime_hours)
        safe_user_agent = user_agent[:500] if isinstance(user_agent, str) else None
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                user = await connection.fetchrow(
                    """SELECT id FROM app_users
                       WHERE id=$1 AND status='active' AND email_verified_at IS NOT NULL
                       FOR UPDATE""",
                    UUID(str(user_id)),
                )
                if user is None:
                    raise ValueError("active_verified_user_required")
                await connection.execute(
                    """INSERT INTO auth_sessions
                       (user_id, token_sha256, created_at, expires_at, last_seen_at, user_agent)
                       VALUES ($1, $2, $3, $4, $3, $5)""",
                    UUID(str(user_id)), token_digest(token), now, expires_at, safe_user_agent,
                )
        # The raw token is returned once. The database stores only its digest.
        return {"token": token, "expires_at": expires_at}

    async def rotate_session(
        self, *, current_token: str, user_agent: str | None = None,
        lifetime_hours: int = 24,
    ) -> dict[str, Any] | None:
        """Atomically replace a live session after re-authentication or privilege changes.

        The current token is consumed exactly once. A missing, expired, revoked, or
        inactive-account session returns None; only the digest of either token is stored.
        """
        if (
            isinstance(lifetime_hours, bool)
            or not isinstance(lifetime_hours, int)
            or not 1 <= lifetime_hours <= 720
        ):
            raise ValueError("session_lifetime_out_of_range")
        try:
            current_digest = token_digest(current_token)
        except ValueError:
            return None
        replacement = new_opaque_token()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=lifetime_hours)
        safe_user_agent = user_agent[:500] if isinstance(user_agent, str) else None
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    """SELECT s.id AS session_id, s.user_id
                       FROM auth_sessions s
                       JOIN app_users u ON u.id=s.user_id
                       WHERE s.token_sha256=$1 AND s.revoked_at IS NULL
                         AND s.expires_at > $2 AND u.status='active'
                         AND u.email_verified_at IS NOT NULL
                       FOR UPDATE OF s""",
                    current_digest, now,
                )
                if current is None:
                    return None
                revoked = await connection.fetchrow(
                    """UPDATE auth_sessions SET revoked_at=$2
                       WHERE id=$1 AND revoked_at IS NULL
                       RETURNING id""",
                    current["session_id"], now,
                )
                if revoked is None:
                    return None
                await connection.execute(
                    """INSERT INTO auth_sessions
                       (user_id, token_sha256, created_at, expires_at, last_seen_at, user_agent)
                       VALUES ($1, $2, $3, $4, $3, $5)""",
                    current["user_id"], token_digest(replacement), now, expires_at,
                    safe_user_agent,
                )
        return {"token": replacement, "expires_at": expires_at}

    async def issue_password_reset(
        self, *, email: str, lifetime_minutes: int = 30,
    ) -> dict[str, Any] | None:
        """Issue a one-time reset token for an eligible account.

        Callers must always return the same public response regardless of this result.
        The raw token is returned once for trusted delivery; only its digest is stored.
        """
        from app.services.auth_security import normalize_email

        normalized_email = normalize_email(email)
        if (
            isinstance(lifetime_minutes, bool)
            or not isinstance(lifetime_minutes, int)
            or not 5 <= lifetime_minutes <= 60
        ):
            raise ValueError("password_reset_lifetime_out_of_range")
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=lifetime_minutes)
        token = new_opaque_token()
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                user = await connection.fetchrow(
                    """SELECT id FROM app_users
                       WHERE email=$1 AND status='active'
                         AND email_verified_at IS NOT NULL
                       FOR UPDATE""",
                    normalized_email,
                )
                if user is None:
                    return None
                await connection.execute(
                    """UPDATE password_reset_tokens SET consumed_at=$2
                       WHERE user_id=$1 AND consumed_at IS NULL""",
                    user["id"], now,
                )
                await connection.execute(
                    """INSERT INTO password_reset_tokens
                       (user_id, token_sha256, created_at, expires_at)
                       VALUES ($1, $2, $3, $4)""",
                    user["id"], token_digest(token), now, expires_at,
                )
        return {"user_id": str(user["id"]), "reset_token": token, "expires_at": expires_at}

    async def reset_password(self, *, token: str, new_password: str) -> bool:
        """Consume one live reset token, update the password, and revoke all sessions."""
        from app.services.auth_security import hash_password

        try:
            digest = token_digest(token)
        except ValueError:
            return False
        if not isinstance(new_password, str) or not 12 <= len(new_password) <= 1024:
            raise ValueError("password_length_out_of_range")
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                # Use the same lock order as issue_password_reset (user, then token)
                # to avoid a deadlock when reset requests race with token re-issuance.
                candidate = await connection.fetchrow(
                    """SELECT id, user_id FROM password_reset_tokens
                       WHERE token_sha256=$1 AND consumed_at IS NULL
                         AND expires_at > $2""",
                    digest, now,
                )
                if candidate is None:
                    return False
                user = await connection.fetchrow(
                    """SELECT id FROM app_users
                       WHERE id=$1 AND status='active'
                         AND email_verified_at IS NOT NULL
                       FOR UPDATE""",
                    candidate["user_id"],
                )
                if user is None:
                    return False
                reset = await connection.fetchrow(
                    """SELECT id AS reset_id, user_id FROM password_reset_tokens
                       WHERE id=$1 AND token_sha256=$2 AND consumed_at IS NULL
                         AND expires_at > $3 FOR UPDATE""",
                    candidate["id"], digest, now,
                )
                if reset is None:
                    return False
                password_hash = hash_password(new_password).encoded
                updated = await connection.fetchrow(
                    """UPDATE app_users SET password_hash=$2, updated_at=$3
                       WHERE id=$1 AND status='active'
                         AND email_verified_at IS NOT NULL
                       RETURNING id""",
                    reset["user_id"], password_hash, now,
                )
                if updated is None:
                    return False
                await connection.execute(
                    """UPDATE password_reset_tokens SET consumed_at=$2
                       WHERE user_id=$1 AND consumed_at IS NULL""",
                    reset["user_id"], now,
                )
                await connection.execute(
                    """UPDATE auth_sessions SET revoked_at=$2
                       WHERE user_id=$1 AND revoked_at IS NULL""",
                    reset["user_id"], now,
                )
                await connection.execute(
                    """INSERT INTO security_audit_events
                       (actor_user_id, event_type, outcome, metadata, created_at)
                       VALUES ($1, 'account.password_reset', 'success',
                               '{}'::jsonb, $2)""",
                    reset["user_id"], now,
                )
                return True

    async def authenticate_session(self, token: str) -> dict[str, Any] | None:
        try:
            digest = token_digest(token)
        except ValueError:
            return None
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT u.id AS user_id, u.email, s.id AS session_id,
                          s.expires_at, s.last_seen_at
                   FROM auth_sessions s
                   JOIN app_users u ON u.id=s.user_id
                   WHERE s.token_sha256=$1 AND s.revoked_at IS NULL
                     AND s.expires_at > $2 AND u.status='active'
                     AND u.email_verified_at IS NOT NULL""",
                digest, now,
            )
        return dict(row) if row is not None else None

    async def revoke_session(self, token: str) -> bool:
        try:
            digest = token_digest(token)
        except ValueError:
            return False
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            result = await connection.execute(
                """UPDATE auth_sessions SET revoked_at=$2
                   WHERE token_sha256=$1 AND revoked_at IS NULL""",
                digest, now,
            )
        return result.endswith(" 1")

    async def authorize_workspace(
        self, *, user_id: UUID | str, workspace_id: str,
        minimum_role: str = "viewer",
    ) -> bool:
        """Check active membership; callers must obtain user_id from authenticate_session."""
        if not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200:
            return False
        if minimum_role not in ROLE_RANK:
            raise ValueError("invalid_minimum_role")
        async with self._pool.acquire() as connection:
            row = await connection.fetchrow(
                """SELECT m.role FROM workspace_memberships m
                   JOIN app_users u ON u.id=m.user_id
                   WHERE m.workspace_id=$1 AND m.user_id=$2
                     AND m.status='active' AND u.status='active'
                     AND u.email_verified_at IS NOT NULL""",
                workspace_id, UUID(str(user_id)),
            )
        if row is None:
            return False
        return row["role"] in ROLE_RANK and ROLE_RANK[row["role"]] >= ROLE_RANK[minimum_role]
