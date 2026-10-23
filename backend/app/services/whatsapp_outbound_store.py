"""Tenant-scoped durable WhatsApp outbound queue; deliberately no provider dispatch."""
from __future__ import annotations

from typing import Any
from uuid import UUID


class WhatsAppOutboundStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def enqueue(
        self, *, workspace_id: str, account_id: UUID, draft_id: UUID,
        actor_id: UUID | str, idempotency_key: str,
    ) -> dict[str, Any]:
        if not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200:
            raise ValueError("workspace_id_invalid")
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 200:
            raise ValueError("idempotency_key_invalid")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                draft = await conn.fetchrow(
                    """SELECT d.id,d.prospect_id,d.status,d.channel,c.status AS campaign_status,
                              p.stage,p.archived_at,a.id AS active_account_id
                       FROM outreach_drafts d
                       JOIN outreach_campaigns c
                         ON c.id=d.campaign_id AND c.workspace_id=d.workspace_id
                       JOIN crm_prospects p
                         ON p.id=d.prospect_id AND p.workspace_id=d.workspace_id
                       JOIN workspace_whatsapp_accounts a
                         ON a.id=$3 AND a.workspace_id=d.workspace_id
                        AND a.status='active' AND a.encrypted_access_token IS NOT NULL
                       WHERE d.id=$2 AND d.workspace_id=$1
                       FOR UPDATE OF d,c,p,a""",
                    workspace_id, draft_id, account_id,
                )
                if draft is None:
                    raise LookupError("workspace_draft_or_account_not_found")
                if draft["channel"] != "whatsapp":
                    raise ValueError("draft_channel_must_be_whatsapp")
                if draft["status"] != "approved" or draft["campaign_status"] != "active":
                    raise ValueError("approved_draft_and_active_campaign_required")
                if draft["archived_at"] is not None:
                    raise ValueError("prospect_archived")
                if draft["stage"] == "do_not_contact":
                    raise ValueError("contact_suppressed")
                existing = await conn.fetchrow(
                    """SELECT id,account_id,draft_id,status,idempotency_key
                       FROM whatsapp_outbound_deliveries
                       WHERE workspace_id=$1 AND (idempotency_key=$2 OR draft_id=$3)
                       FOR UPDATE""",
                    workspace_id, idempotency_key, draft_id,
                )
                if existing is not None:
                    if existing["idempotency_key"] != idempotency_key or existing["draft_id"] != draft_id:
                        raise ValueError("whatsapp_idempotency_conflict")
                    if existing["account_id"] != account_id:
                        raise ValueError("whatsapp_account_conflict")
                    return {"id": str(existing["id"]), "status": existing["status"], "replayed": True}
                row = await conn.fetchrow(
                    """INSERT INTO whatsapp_outbound_deliveries
                       (workspace_id,account_id,draft_id,prospect_id,idempotency_key,queued_by)
                       VALUES($1,$2,$3,$4,$5,$6)
                       RETURNING id,status,queued_at""",
                    workspace_id, account_id, draft_id, draft["prospect_id"],
                    idempotency_key, UUID(str(actor_id)),
                )
                return {
                    "id": str(row["id"]),
                    "status": row["status"],
                    "queued_at": row["queued_at"].isoformat(),
                    "replayed": False,
                }

    async def list(self, *, workspace_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError("pagination_out_of_range")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT q.id,q.account_id,q.draft_id,q.prospect_id,q.status,q.error_code,
                          q.attempts,q.queued_at,q.sent_at,q.updated_at,a.label AS account_label,
                          p.name AS prospect_name
                   FROM whatsapp_outbound_deliveries q
                   JOIN workspace_whatsapp_accounts a
                     ON a.id=q.account_id AND a.workspace_id=q.workspace_id
                   JOIN crm_prospects p
                     ON p.id=q.prospect_id AND p.workspace_id=q.workspace_id
                   WHERE q.workspace_id=$1
                   ORDER BY q.queued_at DESC,q.id LIMIT $2 OFFSET $3""",
                workspace_id, limit, offset,
            )
        items = []
        for raw in rows:
            item = dict(raw)
            for key, value in item.items():
                if isinstance(value, UUID):
                    item[key] = str(value)
                elif hasattr(value, "isoformat"):
                    item[key] = value.isoformat()
            items.append(item)
        return items
