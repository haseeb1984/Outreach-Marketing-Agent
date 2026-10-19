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
