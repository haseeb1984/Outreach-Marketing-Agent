"""Workspace prospect CRM persistence with immutable opt-out state."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID


STAGES = {"researched", "qualified", "drafting", "contacted", "replied", "meeting", "customer", "not_a_fit", "opted_out"}


class WorkspaceProspectStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create(self, *, workspace_id: str, user_id: str, campaign_id: UUID,
                     display_name: str, organization_name: str | None, website_url: str,
                     contact_email: str | None, contact_phone: str | None,
                     source_url: str, fit_reason: str, notes: str | None = None) -> dict[str, Any]:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """INSERT INTO workspace_prospects
                       (workspace_id, campaign_id, created_by, display_name, organization_name,
                        website_url, contact_email, contact_phone, source_url, fit_reason, notes)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING *""",
                    workspace_id, campaign_id, UUID(str(user_id)), display_name.strip(),
                    organization_name.strip() if organization_name else None, website_url.strip(),
                    contact_email.strip().lower() if contact_email else None,
                    contact_phone.strip() if contact_phone else None, source_url.strip(),
                    fit_reason.strip(), notes.strip() if notes else None,
                )
                await connection.execute(
                    """INSERT INTO security_audit_events
                       (workspace_id, actor_user_id, event_type, outcome, metadata)
                       VALUES ($1,$2,'prospect.created','success',$3::jsonb)""",
                    workspace_id, UUID(str(user_id)),
                    json.dumps({"prospect_id": str(row["id"]), "campaign_id": str(campaign_id)}),
                )
        return self._public(row)

    async def list_for_workspace(self, *, workspace_id: str, campaign_id: UUID | None,
                                 stage: str | None, limit: int = 50) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("invalid_limit")
        if stage is not None and stage not in STAGES:
            raise ValueError("invalid_stage")
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                """SELECT * FROM workspace_prospects
                   WHERE workspace_id=$1 AND ($2::uuid IS NULL OR campaign_id=$2)
                     AND ($3::text IS NULL OR stage=$3)
                   ORDER BY created_at DESC, id DESC LIMIT $4""",
                workspace_id, campaign_id, stage, limit,
            )
        return [self._public(row) for row in rows]

    async def update_stage(self, *, workspace_id: str, user_id: str, prospect_id: UUID,
                           stage: str, note: str | None = None) -> dict[str, Any] | None:
        if stage not in STAGES:
            raise ValueError("invalid_stage")
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """UPDATE workspace_prospects SET
                         stage=CASE WHEN opt_out THEN 'opted_out' ELSE $3 END,
                         opt_out=opt_out OR $3='opted_out',
                         opt_out_at=CASE WHEN opt_out OR $3='opted_out' THEN COALESCE(opt_out_at,now()) ELSE NULL END,
                         notes=CASE WHEN $4::text IS NULL THEN notes ELSE $4 END,
                         updated_at=now()
                       WHERE workspace_id=$1 AND id=$2 RETURNING *""",
                    workspace_id, prospect_id, stage, note.strip() if note else None,
                )
                if row:
                    await connection.execute(
                        """INSERT INTO security_audit_events
                           (workspace_id, actor_user_id, event_type, outcome, metadata)
                           VALUES ($1,$2,'prospect.stage_changed','success',$3::jsonb)""",
                        workspace_id, UUID(str(user_id)),
                        json.dumps({"prospect_id": str(prospect_id), "stage": row["stage"]}),
                    )
        return self._public(row) if row else None

    @staticmethod
    def _public(row: Any) -> dict[str, Any]:
        result = dict(row)
        for key in ("id", "workspace_id", "campaign_id", "created_by"):
            if result.get(key) is not None:
                result[key] = str(result[key])
        for key in ("opt_out_at", "created_at", "updated_at"):
            if result.get(key) is not None:
                result[key] = result[key].isoformat()
        return result
