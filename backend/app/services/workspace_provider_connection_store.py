"""Persistence for provider connection intents and safe connection metadata.

This layer deliberately cannot mark a provider as connected: OAuth/provider validation and
secret-manager operations must be implemented before that state is reachable.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID


PROVIDERS = {"email", "whatsapp"}


class WorkspaceProviderConnectionStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create_pending(self, *, workspace_id: str, user_id: str,
                             provider: str, display_label: str) -> dict[str, Any]:
        if provider not in PROVIDERS:
            raise ValueError("invalid_provider")
        label = display_label.strip()
        if not 1 <= len(label) <= 160:
            raise ValueError("invalid_display_label")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """INSERT INTO workspace_provider_connections
                       (workspace_id, provider, display_label, status, created_by)
                       VALUES ($1,$2,$3,'pending',$4)
                       RETURNING id, workspace_id, provider, display_label, status,
                                 granted_scopes, token_expires_at, last_validated_at,
                                 last_error_code, created_by, created_at, updated_at, revoked_at""",
                    workspace_id, provider, label, UUID(str(user_id)),
                )
                await connection.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id, actor_user_id, event_type, outcome, metadata)
                       VALUES ($1,$2,'provider_connection.intent_created','success',$3::jsonb)""",
                    workspace_id, UUID(str(user_id)),
                    json.dumps({"connection_id": str(row["id"]), "provider": provider}),
                )
        return self._public(row)

    async def list_for_workspace(self, *, workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("invalid_limit")
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                """SELECT id, workspace_id, provider, display_label, status, granted_scopes,
                          token_expires_at, last_validated_at, last_error_code, created_by,
                          created_at, updated_at, revoked_at
                   FROM workspace_provider_connections
                   WHERE workspace_id=$1
                   ORDER BY created_at DESC, id DESC LIMIT $2""",
                workspace_id, limit,
            )
        return [self._public(row) for row in rows]

    async def cancel_pending(self, *, workspace_id: str, connection_id: UUID, user_id: str) -> dict[str, Any] | None:
        """Cancel an intent that has no provider credentials attached."""
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """UPDATE workspace_provider_connections
                       SET status='revoked', revoked_at=now(), updated_at=now()
                       WHERE workspace_id=$1 AND id=$2 AND status='pending'
                       RETURNING id, workspace_id, provider, display_label, status, granted_scopes,
                                 token_expires_at, last_validated_at, last_error_code, created_by,
                                 created_at, updated_at, revoked_at""",
                    workspace_id, connection_id,
                )
                if row is None:
                    return None
                await connection.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id, actor_user_id, event_type, outcome, metadata)
                       VALUES ($1,$2,'provider_connection.intent_cancelled','success',$3::jsonb)""",
                    workspace_id, UUID(str(user_id)),
                    json.dumps({"connection_id": str(connection_id), "provider": row["provider"]}),
                )
        return self._public(row)

    @staticmethod
    def _public(row: Any) -> dict[str, Any]:
        result = dict(row)
        # Explicit allowlist means secret_reference and provider credentials never serialize.
        allowed = {
            "id", "workspace_id", "provider", "display_label", "status", "granted_scopes",
            "token_expires_at", "last_validated_at", "last_error_code", "created_by",
            "created_at", "updated_at", "revoked_at",
        }
        result = {key: value for key, value in result.items() if key in allowed}
        for key in ("id", "workspace_id", "created_by"):
            if result.get(key) is not None:
                result[key] = str(result[key])
        for key in ("token_expires_at", "last_validated_at", "created_at", "updated_at", "revoked_at"):
            if result.get(key) is not None:
                result[key] = result[key].isoformat()
        return result
