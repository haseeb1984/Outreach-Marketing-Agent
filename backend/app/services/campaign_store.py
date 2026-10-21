"""Workspace-scoped campaign and human-review persistence; never sends messages."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.services.prospect_outreach import draft_outreach


class CampaignStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create_campaign(self, *, workspace_id: str, created_by: UUID | str, name: str,
                              client_business: str, client_offer: str,
                              target_customer_profile: str) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO outreach_campaigns
                   (workspace_id,created_by,name,client_business,client_offer,target_customer_profile)
                   VALUES ($1,$2,$3,$4,$5,$6)
                   RETURNING id,workspace_id,name,client_business,client_offer,target_customer_profile,status,created_by,created_at,updated_at""",
                workspace_id, UUID(str(created_by)), name.strip(), client_business.strip(),
                client_offer.strip(), target_customer_profile.strip(),
            )
        return self._serialize(dict(row))

    async def list_campaigns(self, *, workspace_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        self._validate_page(limit, offset)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id,workspace_id,name,client_business,client_offer,target_customer_profile,
                          status,created_by,created_at,updated_at
                   FROM outreach_campaigns WHERE workspace_id=$1 AND status <> 'archived'
                   ORDER BY updated_at DESC,id LIMIT $2 OFFSET $3""",
                workspace_id, limit, offset,
            )
        return [self._serialize(dict(row)) for row in rows]

    async def create_draft(self, *, workspace_id: str, campaign_id: UUID, prospect_id: UUID,
                           actor_id: UUID | str, channel: str, call_to_action: str,
                           whatsapp_opt_in_confirmed: bool) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                campaign = await conn.fetchrow(
                    """SELECT * FROM outreach_campaigns WHERE id=$1 AND workspace_id=$2 AND status <> 'archived' FOR SHARE""",
                    campaign_id, workspace_id,
                )
                prospect = await conn.fetchrow(
                    """SELECT * FROM crm_prospects WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL FOR SHARE""",
                    prospect_id, workspace_id,
                )
                if campaign is None or prospect is None:
                    return None
                p = dict(prospect)
                facts = self._json_list(p.get("verified_facts"))
                draft = draft_outreach(
                    channel=channel,
                    client_business=campaign["client_business"],
                    client_offer=campaign["client_offer"],
                    prospect_name=p["name"],
                    prospect_evidence_url=p["evidence_url"],
                    verified_relevance=p["fit_reason"],
                    verified_facts=facts,
                    call_to_action=call_to_action,
                    whatsapp_opt_in_confirmed=whatsapp_opt_in_confirmed,
                )
                row = await conn.fetchrow(
                    """INSERT INTO outreach_drafts
                       (workspace_id,campaign_id,prospect_id,channel,subject,body,source_evidence_url,
                        verified_facts_used,created_by)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
                       RETURNING *""",
                    workspace_id, campaign_id, prospect_id, channel, draft["subject"], draft["body"],
                    draft["source_evidence_url"], json.dumps(draft["verified_facts_used"]), UUID(str(actor_id)),
                )
                await conn.execute(
                    """INSERT INTO outreach_draft_events(draft_id,workspace_id,actor_id,event_type)
                       VALUES ($1,$2,$3,'created')""",
                    row["id"], workspace_id, UUID(str(actor_id)),
                )
        return self._serialize(dict(row))

    async def list_drafts(self, *, workspace_id: str, status: str = "pending_approval",
                          limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        self._validate_page(limit, offset)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM outreach_drafts WHERE workspace_id=$1 AND ($2::text IS NULL OR status=$2)
                   ORDER BY created_at DESC,id LIMIT $3 OFFSET $4""",
                workspace_id, None if status == "all" else status, limit, offset,
            )
        return [self._serialize(dict(row)) for row in rows]

    async def review_draft(self, *, workspace_id: str, draft_id: UUID, actor_id: UUID | str,
                           decision: str, note: str | None = None) -> dict[str, Any] | None:
        if decision not in {"approved", "rejected"}:
            raise ValueError("invalid_review_decision")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """UPDATE outreach_drafts SET status=$3,reviewed_by=$4,reviewed_at=now(),
                              review_note=$5,updated_at=now()
                       WHERE id=$1 AND workspace_id=$2 AND status='pending_approval'
                       RETURNING *""",
                    draft_id, workspace_id, decision, UUID(str(actor_id)), note.strip() if note else None,
                )
                if row is None:
                    return None
                await conn.execute(
                    """INSERT INTO outreach_draft_events(draft_id,workspace_id,actor_id,event_type,note)
                       VALUES ($1,$2,$3,$4,$5)""",
                    draft_id, workspace_id, UUID(str(actor_id)), decision, note.strip() if note else None,
                )
        return self._serialize(dict(row))

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        if not 1 <= limit <= 100 or not 0 <= offset <= 100_000:
            raise ValueError("pagination_out_of_range")

    @staticmethod
    def _json_list(value: Any) -> list[str]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = []
        return value if isinstance(value, list) and all(isinstance(v, str) for v in value) else []

    @classmethod
    def _serialize(cls, row: dict[str, Any]) -> dict[str, Any]:
        for key in ("id", "created_by", "reviewed_by", "campaign_id", "prospect_id"):
            if row.get(key) is not None:
                row[key] = str(row[key])
        if "verified_facts_used" in row:
            row["verified_facts_used"] = cls._json_list(row["verified_facts_used"])
        return row
