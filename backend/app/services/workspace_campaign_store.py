"""Persistence for workspace-scoped outreach campaigns."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID


class WorkspaceCampaignStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create(
        self, *, workspace_id: str, user_id: str, name: str,
        website_url: str, goal: str, channel: str,
    ) -> dict[str, Any]:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """INSERT INTO workspace_campaigns
                       (workspace_id, created_by, name, website_url, goal, channel)
                       VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
                    workspace_id, UUID(str(user_id)), name.strip(),
                    website_url.strip(), goal, channel,
                )
                await connection.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id, actor_user_id, event_type, outcome, metadata)
                       VALUES ($1, $2, 'campaign.created', 'success', $3::jsonb)""",
                    workspace_id, UUID(str(user_id)),
                    json.dumps({"campaign_id": str(row["id"]), "goal": goal, "channel": channel}),
                )
        return self._public(row)

    async def list_for_workspace(
        self, *, workspace_id: str, limit: int = 50, status: str | None = None,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("invalid_limit")
        async with self._pool.acquire() as connection:
            if status is None:
                rows = await connection.fetch(
                    """SELECT * FROM workspace_campaigns WHERE workspace_id=$1
                       ORDER BY created_at DESC, id DESC LIMIT $2""", workspace_id, limit,
                )
            else:
                rows = await connection.fetch(
                    """SELECT * FROM workspace_campaigns WHERE workspace_id=$1 AND status=$2
                       ORDER BY created_at DESC, id DESC LIMIT $3""", workspace_id, status, limit,
                )
        return [self._public(row) for row in rows]

    async def transition_status(
        self, *, workspace_id: str, campaign_id: UUID, user_id: str, status: str,
    ) -> dict[str, Any] | None:
        """Apply an explicit campaign lifecycle transition atomically."""
        transitions = {
            "draft": {"active", "archived"},
            "active": {"paused", "completed"},
            "paused": {"active", "completed", "archived"},
            "completed": {"archived"},
            "archived": set(),
        }
        if status not in transitions:
            raise ValueError("invalid_campaign_status")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    """SELECT id, status FROM workspace_campaigns
                       WHERE workspace_id=$1 AND id=$2 FOR UPDATE""",
                    workspace_id, campaign_id,
                )
                if current is None:
                    return None
                previous = str(current["status"])
                if status == previous:
                    raise ValueError("campaign_status_unchanged")
                if status not in transitions.get(previous, set()):
                    raise ValueError("invalid_campaign_transition")
                row = await connection.fetchrow(
                    """UPDATE workspace_campaigns SET status=$3, updated_at=now()
                       WHERE workspace_id=$1 AND id=$2 RETURNING *""",
                    workspace_id, campaign_id, status,
                )
                await connection.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id, actor_user_id, event_type, outcome, metadata)
                       VALUES ($1, $2, 'campaign.status_changed', 'success', $3::jsonb)""",
                    workspace_id, UUID(str(user_id)),
                    json.dumps({"campaign_id": str(campaign_id), "from": previous, "to": status}),
                )
        return self._public(row)

    @staticmethod
    def _public(row: Any) -> dict[str, Any]:
        result = dict(row)
        for key in ("id", "workspace_id", "created_by"):
            if result.get(key) is not None:
                result[key] = str(result[key])
        for key in ("starts_at", "ends_at", "created_at", "updated_at"):
            if result.get(key) is not None:
                result[key] = result[key].isoformat()
        return result
