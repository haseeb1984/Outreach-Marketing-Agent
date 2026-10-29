"""Tenant-scoped durable WhatsApp outbound queue; deliberately no provider dispatch."""
from __future__ import annotations

from typing import Any
from uuid import UUID


class WhatsAppOutboundStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def enqueue(
        self, *, workspace_id: str, account_id: UUID, draft_id: UUID,
        actor_id: UUID | str, idempotency_key: str, usage_reservation_id: UUID | str,
        template_name: str | None = None, language_code: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200:
            raise ValueError("workspace_id_invalid")
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 200:
            raise ValueError("idempotency_key_invalid")
        try:
            reservation_uuid = UUID(str(usage_reservation_id))
            actor_uuid = UUID(str(actor_id))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("whatsapp_identity_uuid_invalid") from None
        if (template_name is None) != (language_code is None):
            raise ValueError("whatsapp_template_metadata_pair_required")
        if template_name is not None:
            if not template_name.strip() or len(template_name) > 512:
                raise ValueError("whatsapp_template_name_invalid")
            import re
            if not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", language_code or ""):
                raise ValueError("whatsapp_template_language_invalid")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                draft = await conn.fetchrow(
                    """SELECT d.id,d.prospect_id,d.status,d.channel,c.status AS campaign_status,
                              p.stage,p.archived_at,p.contact_phone_e164,
                              cc.whatsapp_opt_in_at,cc.whatsapp_opt_in_evidence_url,
                              cc.whatsapp_account_id,a.id AS active_account_id
                       FROM outreach_drafts d
                       JOIN outreach_campaigns c
                         ON c.id=d.campaign_id AND c.workspace_id=d.workspace_id
                       JOIN crm_prospects p
                         ON p.id=d.prospect_id AND p.workspace_id=d.workspace_id
                       JOIN outreach_contact_controls cc
                         ON cc.prospect_id=p.id AND cc.workspace_id=d.workspace_id
                       JOIN workspace_whatsapp_accounts a
                         ON a.id=$3 AND a.workspace_id=d.workspace_id
                        AND a.status='active' AND a.encrypted_access_token IS NOT NULL
                       WHERE d.id=$2 AND d.workspace_id=$1
                       FOR UPDATE OF d,c,p,cc,a""",
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
                if (
                    draft["whatsapp_opt_in_at"] is None
                    or not draft["whatsapp_opt_in_evidence_url"]
                    or draft["whatsapp_account_id"] != account_id
                ):
                    raise ValueError("documented_whatsapp_opt_in_for_account_required")
                phone = "".join(
                    ch for ch in str(draft["contact_phone_e164"] or "") if ch.isdigit()
                )
                if not phone:
                    raise ValueError("prospect_whatsapp_phone_required")
                preference = await conn.fetchrow(
                    """SELECT opted_out_at,opted_in_at
                       FROM whatsapp_contact_preferences
                       WHERE workspace_id=$1 AND account_id=$2 AND wa_id=$3
                       FOR UPDATE""",
                    workspace_id, account_id, phone,
                )
                if preference is not None and preference["opted_out_at"] is not None:
                    opted_in_at = preference["opted_in_at"]
                    if opted_in_at is None or preference["opted_out_at"] >= opted_in_at:
                        raise ValueError("whatsapp_contact_opted_out")
                existing = await conn.fetchrow(
                    """SELECT id,account_id,draft_id,status,idempotency_key,usage_reservation_id,
                              template_name,language_code
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
                    if existing["usage_reservation_id"] != reservation_uuid:
                        raise ValueError("whatsapp_reservation_conflict")
                    if (existing["template_name"], existing["language_code"]) != (template_name, language_code):
                        raise ValueError("whatsapp_template_metadata_conflict")
                    return {
                        "id": str(existing["id"]),
                        "status": existing["status"],
                        "usage_reservation_id": str(existing["usage_reservation_id"]),
                        "template_name": existing["template_name"],
                        "language_code": existing["language_code"],
                        "replayed": True,
                    }
                row = await conn.fetchrow(
                    """INSERT INTO whatsapp_outbound_deliveries
                       (workspace_id,account_id,draft_id,prospect_id,idempotency_key,usage_reservation_id,queued_by,
                        template_name,language_code)
                       VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                       RETURNING id,status,queued_at""",
                    workspace_id, account_id, draft_id, draft["prospect_id"],
                    idempotency_key, reservation_uuid, actor_uuid,
                    template_name, language_code,
                )
                return {
                    "id": str(row["id"]),
                    "status": row["status"],
                    "queued_at": row["queued_at"].isoformat(),
                    "usage_reservation_id": str(reservation_uuid),
                    "template_name": template_name,
                    "language_code": language_code,
                    "replayed": False,
                }

    async def find_by_idempotency_key(
        self, *, workspace_id: str, idempotency_key: str,
    ) -> dict[str, Any] | None:
        """Return a workspace-scoped queue record so client retries can replay safely."""
        if not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200:
            raise ValueError("workspace_id_invalid")
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 200:
            raise ValueError("idempotency_key_invalid")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id,account_id,draft_id,status,queued_at,template_name,language_code
                   FROM whatsapp_outbound_deliveries
                   WHERE workspace_id=$1 AND idempotency_key=$2""",
                workspace_id, idempotency_key,
            )
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "account_id": str(row["account_id"]),
            "draft_id": str(row["draft_id"]),
            "status": row["status"],
            "queued_at": row["queued_at"].isoformat(),
            "template_name": row["template_name"],
            "language_code": row["language_code"],
            "replayed": True,
        }


    async def claim_batch(self, *, limit: int = 10, lease_seconds: int = 120) -> list[dict[str, Any]]:
        """Atomically claim queued rows using SKIP LOCKED; each claim gets a unique lease.

        This only manages queue state. It intentionally does not dispatch provider
        messages or automatically reclaim expired processing rows for another send.
        """
        if not 1 <= limit <= 100:
            raise ValueError("claim_limit_out_of_range")
        if not 15 <= lease_seconds <= 900:
            raise ValueError("lease_seconds_out_of_range")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """WITH candidates AS (
                       SELECT id FROM whatsapp_outbound_deliveries
                       WHERE status='queued'
                       ORDER BY queued_at,id
                       FOR UPDATE SKIP LOCKED
                       LIMIT $1
                   )
                   UPDATE whatsapp_outbound_deliveries q
                   SET status='processing', attempts=q.attempts+1,
                       processing_at=now(), lease_token=gen_random_uuid(),
                       lease_expires_at=now()+($2::int * interval '1 second'),
                       updated_at=now()
                   FROM candidates c
                   WHERE q.id=c.id
                   RETURNING q.id,q.workspace_id,q.account_id,q.draft_id,q.prospect_id,
                             q.usage_reservation_id,q.template_name,q.language_code,
                             q.status,q.attempts,q.lease_token,q.lease_expires_at""",
                limit, lease_seconds,
            )
        result = []
        for row in rows:
            item = dict(row)
            for key, value in item.items():
                if isinstance(value, UUID):
                    item[key] = str(value)
                elif hasattr(value, "isoformat"):
                    item[key] = value.isoformat()
            result.append(item)
        return result

    async def finish_claim(
        self, *, delivery_id: UUID, lease_token: UUID, outcome: str,
        provider_message_id: str | None = None, error_code: str | None = None,
    ) -> bool:
        """Finish only the exact live lease; stale workers cannot overwrite newer state."""
        allowed = {"sent", "failed", "uncertain", "cancelled"}
        if outcome not in allowed:
            raise ValueError("invalid_delivery_outcome")
        if provider_message_id is not None and (
            not provider_message_id.strip() or len(provider_message_id) > 256
        ):
            raise ValueError("provider_message_id_invalid")
        if error_code is not None and (
            not error_code.strip() or len(error_code) > 100
        ):
            raise ValueError("delivery_error_code_invalid")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE whatsapp_outbound_deliveries
                   SET status=$3::text, provider_message_id=$4, error_code=$5,
                       sent_at=CASE WHEN $3::text='sent' THEN now() ELSE sent_at END,
                       lease_token=NULL, lease_expires_at=NULL, updated_at=now()
                   WHERE id=$1 AND lease_token=$2 AND status='processing'
                     AND lease_expires_at > now()
                   RETURNING id""",
                delivery_id, lease_token, outcome, provider_message_id, error_code,
            )
        return row is not None

    async def mark_expired_claims_uncertain(self, *, limit: int = 100) -> int:
        """Recover expired sends as uncertain and settle their reserved quota atomically."""
        if not 1 <= limit <= 1000:
            raise ValueError("recovery_limit_out_of_range")
        async with self._pool.acquire() as conn:
            recovered_count = await conn.fetchval(
                """WITH expired AS (
                       SELECT id FROM whatsapp_outbound_deliveries
                       WHERE status='processing' AND lease_expires_at <= now()
                       ORDER BY lease_expires_at,id
                       FOR UPDATE SKIP LOCKED
                       LIMIT $1
                   ), recovered AS (
                       UPDATE whatsapp_outbound_deliveries q
                       SET status='uncertain', error_code='worker_lease_expired',
                           lease_token=NULL, lease_expires_at=NULL, updated_at=now()
                       FROM expired e
                       WHERE q.id=e.id
                       RETURNING q.workspace_id,q.usage_reservation_id
                   ), settled AS (
                       UPDATE feature_usage_reservations r
                       SET status='consumed',updated_at=now()
                       FROM recovered q
                       WHERE r.id=q.usage_reservation_id
                         AND r.workspace_id=q.workspace_id
                         AND r.status='reserved'
                       RETURNING r.id
                   )
                   SELECT count(*) FROM recovered""",
                limit,
            )
        return int(recovered_count or 0)

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
