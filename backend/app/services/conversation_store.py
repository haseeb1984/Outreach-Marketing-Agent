"""Persistence for verified inbound replies; provider payloads are not logged."""
from __future__ import annotations
from typing import Any
from uuid import UUID

class ConversationStore:
    def __init__(self,pool: Any)->None: self._pool=pool

    async def ingest_reply(self,*,workspace_id: str,prospect_id: UUID,provider: str,event_id: str,
                           message_id: str,in_reply_to: str|None,channel: str,body: str,occurred_at: Any)->dict[str,Any]:
        async with self._pool.acquire() as c:
            async with c.transaction():
                prospect=await c.fetchrow("""SELECT id FROM crm_prospects WHERE id=$1 AND workspace_id=$2
                    AND archived_at IS NULL FOR UPDATE""",prospect_id,workspace_id)
                if prospect is None: raise LookupError("prospect_not_found")
                row=await c.fetchrow("""INSERT INTO outreach_conversation_messages
                    (workspace_id,prospect_id,provider,provider_event_id,provider_message_id,
                     in_reply_to_provider_message_id,channel,direction,body,occurred_at)
                    VALUES($1,$2,$3,$4,$5,$6,$7,'inbound',$8,$9)
                    ON CONFLICT(provider,provider_event_id) DO NOTHING
                    RETURNING id,workspace_id,prospect_id,provider,provider_event_id,provider_message_id,
                              in_reply_to_provider_message_id,channel,direction,body,occurred_at,received_at""",
                    workspace_id,prospect_id,provider,event_id,message_id,in_reply_to,channel,body,occurred_at)
                if row is None:
                    return {"duplicate":True,"event_id":event_id}
                await c.execute("""UPDATE crm_prospects SET stage='replied',updated_at=now()
                    WHERE id=$1 AND workspace_id=$2 AND stage NOT IN ('do_not_contact','disqualified')""",
                    prospect_id,workspace_id)
                # A reply ends the active outreach cycle. Cancel every not-yet-claimed
                # email delivery in this transaction; the send worker rechecks stage
                # while claiming to close the race with concurrent sends.
                await c.execute("""UPDATE outreach_deliveries
                    SET status='cancelled',error_code='prospect_replied',updated_at=now()
                    WHERE workspace_id=$1 AND status='queued'
                      AND draft_id IN (
                        SELECT id FROM outreach_drafts
                        WHERE workspace_id=$1 AND prospect_id=$2
                      )""", workspace_id, prospect_id)
                result=dict(row)
                for k in ("id","prospect_id"): result[k]=str(result[k])
                return {"duplicate":False,"message":result}

    async def list_messages(self, *, workspace_id: str, prospect_id: UUID, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Return chronological email and WhatsApp inbound conversation history."""
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError("pagination_out_of_range")
        async with self._pool.acquire() as c:
            rows = await c.fetch("""WITH all_messages AS (
                SELECT id::text AS id,workspace_id,prospect_id,provider,provider_event_id,
                       provider_message_id,in_reply_to_provider_message_id,channel,direction,body,
                       occurred_at,received_at,NULL::text AS delivery_status
                FROM outreach_conversation_messages
                WHERE workspace_id=$1 AND prospect_id=$2
                UNION ALL
                SELECT m.id::text,m.workspace_id,c.prospect_id,'meta_whatsapp',NULL,
                       m.provider_message_id,NULL,'whatsapp','inbound',
                       COALESCE(m.text_body,'[' || m.message_type || ']'),
                       COALESCE(m.provider_timestamp,m.received_at),m.received_at,NULL::text
                FROM whatsapp_inbound_messages m
                JOIN whatsapp_conversations c ON c.id=m.conversation_id AND c.workspace_id=m.workspace_id
                WHERE m.workspace_id=$1 AND c.prospect_id=$2
                UNION ALL
                SELECT q.id::text,q.workspace_id,d.prospect_id,'smtp',NULL,q.provider_message_id,
                       NULL,'email','outbound',d.body,COALESCE(q.sent_at,q.updated_at,q.queued_at),
                       q.queued_at,q.status::text
                FROM outreach_deliveries q
                JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                WHERE q.workspace_id=$1 AND d.prospect_id=$2 AND q.status IN ('sent','failed')
                UNION ALL
                SELECT q.id::text,q.workspace_id,q.prospect_id,'meta_whatsapp',NULL,q.provider_message_id,
                       NULL,'whatsapp','outbound',d.body,COALESCE(q.sent_at,q.updated_at,q.queued_at),
                       q.queued_at,q.status::text
                FROM whatsapp_outbound_deliveries q
                JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                WHERE q.workspace_id=$1 AND q.prospect_id=$2
                  AND q.status IN ('sent','delivered','read','failed','uncertain')
            )
            SELECT * FROM (
                SELECT * FROM all_messages
                ORDER BY occurred_at DESC,id DESC
                LIMIT $3 OFFSET $4
            ) latest_page
            ORDER BY occurred_at ASC,id ASC""", workspace_id, prospect_id, limit, offset)
        result = []
        for row in rows:
            item = dict(row)
            item["id"] = str(item["id"])
            item["prospect_id"] = str(item["prospect_id"])
            result.append(item)
        return result

    async def list_threads(self, *, workspace_id: str, limit: int = 50, offset: int = 0, search: str = "", project_id: UUID | None = None) -> list[dict[str, Any]]:
        """Return one cross-channel thread per prospect, including native Meta inbox messages."""
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError("pagination_out_of_range")
        async with self._pool.acquire() as c:
            rows = await c.fetch("""WITH all_messages AS (
                SELECT id::text AS id, prospect_id, channel, body, provider, occurred_at, received_at,
                       'inbound'::text AS direction,NULL::text AS delivery_status
                FROM outreach_conversation_messages WHERE workspace_id=$1
                UNION ALL
                SELECT m.id::text, c.prospect_id, 'whatsapp', COALESCE(m.text_body,'[' || m.message_type || ']'),
                       'meta_whatsapp', COALESCE(m.provider_timestamp,m.received_at), m.received_at,
                       'inbound'::text,NULL::text
                FROM whatsapp_inbound_messages m
                JOIN whatsapp_conversations c ON c.id=m.conversation_id AND c.workspace_id=m.workspace_id
                WHERE m.workspace_id=$1 AND c.prospect_id IS NOT NULL
                UNION ALL
                SELECT q.id::text,d.prospect_id,'email',d.body,'smtp',
                       COALESCE(q.sent_at,q.updated_at,q.queued_at),q.queued_at,'outbound',q.status::text
                FROM outreach_deliveries q
                JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                WHERE q.workspace_id=$1 AND q.status IN ('sent','failed')
                UNION ALL
                SELECT q.id::text,q.prospect_id,'whatsapp',d.body,'meta_whatsapp',
                       COALESCE(q.sent_at,q.updated_at,q.queued_at),q.queued_at,'outbound',q.status::text
                FROM whatsapp_outbound_deliveries q
                JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                WHERE q.workspace_id=$1 AND q.status IN ('sent','delivered','read','failed','uncertain')
            ), ranked AS (
                SELECT message.*, row_number() OVER (PARTITION BY message.prospect_id
                    ORDER BY message.occurred_at DESC,message.id DESC) AS position,
                    count(*) OVER (PARTITION BY message.prospect_id) AS message_count
                FROM all_messages message
                JOIN crm_prospects p ON p.id=message.prospect_id AND p.workspace_id=$1 AND p.archived_at IS NULL
            )
            SELECT ranked.id, ranked.prospect_id, p.name AS prospect_name,p.company AS prospect_company,
                   p.contact_email,p.contact_phone_e164,ranked.channel,ranked.body AS latest_message,
                   ranked.provider,ranked.direction AS latest_direction,ranked.delivery_status AS latest_delivery_status,ranked.occurred_at AS latest_message_at,ranked.received_at,ranked.message_count
            FROM ranked JOIN crm_prospects p ON p.id=ranked.prospect_id
            WHERE ranked.position=1
              AND ($4 = '' OR p.name ILIKE $5 OR COALESCE(p.company,'') ILIKE $5
                   OR ranked.body ILIKE $5 OR ranked.channel ILIKE $5)
              AND ($6::uuid IS NULL OR p.project_id=$6)
            ORDER BY ranked.occurred_at DESC,ranked.id DESC LIMIT $2 OFFSET $3""",
                workspace_id, limit, offset, search.strip(), '%' + search.strip() + '%', project_id)
        result = []
        for row in rows:
            item = dict(row)
            item["id"] = str(item["id"])
            item["prospect_id"] = str(item["prospect_id"])
            result.append(item)
        return result

    async def create_reply_draft(self, *, workspace_id: str, prospect_id: UUID, actor_id: UUID | str,
                                channel: str, subject: str | None, body: str) -> dict[str, Any]:
        """Create a human-review-required reply draft; never dispatch from the inbox."""
        if channel not in {"email", "whatsapp"}:
            raise ValueError("reply_channel_invalid")
        if not isinstance(body, str) or not body.strip() or len(body.strip()) > 10000:
            raise ValueError("reply_body_invalid")
        if channel == "email" and (not isinstance(subject, str) or not subject.strip() or len(subject.strip()) > 300):
            raise ValueError("reply_subject_required")
        actor = UUID(str(actor_id))
        async with self._pool.acquire() as c:
            async with c.transaction():
                prospect = await c.fetchrow("""SELECT id,stage,archived_at,contact_email,contact_phone_e164,
                           evidence_url FROM crm_prospects
                       WHERE id=$1 AND workspace_id=$2 FOR UPDATE""", prospect_id, workspace_id)
                if prospect is None or prospect["archived_at"] is not None:
                    raise LookupError("prospect_not_found")
                if not isinstance(prospect["evidence_url"], str) or not prospect["evidence_url"].lower().startswith("https://"):
                    raise ValueError("reply_source_evidence_required")
                if channel == "email":
                    if not prospect["contact_email"]:
                        raise ValueError("reply_email_contact_missing")
                    suppressed = await c.fetchval("""SELECT COALESCE(email_suppressed,FALSE)
                        FROM outreach_contact_controls WHERE workspace_id=$1 AND prospect_id=$2""", workspace_id, prospect_id)
                    if suppressed:
                        raise ValueError("reply_email_contact_suppressed")
                else:
                    phone = "".join(ch for ch in str(prospect["contact_phone_e164"] or "") if ch.isdigit())
                    if not phone:
                        raise ValueError("reply_whatsapp_contact_missing")
                    consent = await c.fetchrow("""SELECT whatsapp_opt_in_at,whatsapp_opt_in_evidence_url,whatsapp_account_id
                        FROM outreach_contact_controls WHERE workspace_id=$1 AND prospect_id=$2 FOR UPDATE""",
                        workspace_id, prospect_id)
                    if consent is None or consent["whatsapp_opt_in_at"] is None or not consent["whatsapp_opt_in_evidence_url"] or not consent["whatsapp_account_id"]:
                        raise ValueError("reply_whatsapp_consent_required")
                    opted_out = await c.fetchval("""SELECT EXISTS(SELECT 1 FROM whatsapp_contact_preferences
                        WHERE workspace_id=$1 AND wa_id=$2 AND opted_out_at IS NOT NULL
                          AND (opted_in_at IS NULL OR opted_out_at >= opted_in_at))""", workspace_id, phone)
                    if opted_out:
                        raise ValueError("reply_whatsapp_contact_opted_out")
                campaign_id = await c.fetchval("""SELECT d.campaign_id FROM outreach_drafts d
                    JOIN outreach_campaigns cp ON cp.id=d.campaign_id AND cp.workspace_id=d.workspace_id
                    WHERE d.workspace_id=$1 AND d.prospect_id=$2 AND cp.status='active'
                    ORDER BY d.created_at DESC,d.id DESC LIMIT 1""", workspace_id, prospect_id)
                if campaign_id is None:
                    raise ValueError("reply_active_campaign_required")
                try:
                    draft = await c.fetchrow("""INSERT INTO outreach_drafts
                        (workspace_id,campaign_id,prospect_id,channel,subject,body,source_evidence_url,
                         verified_facts_used,status,created_by)
                        VALUES($1,$2,$3,$4,$5,$6,$7,'[]'::jsonb,'pending_approval',$8)
                        RETURNING id,workspace_id,campaign_id,prospect_id,channel,subject,body,status,created_at""",
                        workspace_id,campaign_id,prospect_id,channel,subject.strip() if subject else None,
                        body.strip(),prospect["evidence_url"],actor)
                except Exception as exc:
                    if "unique" in str(exc).lower():
                        raise ValueError("reply_pending_draft_exists") from None
                    raise
                await c.execute("""INSERT INTO outreach_draft_events
                    (draft_id,workspace_id,actor_id,event_type,note)
                    VALUES($1,$2,$3,'created',$4)""", draft["id"],workspace_id,actor,
                    "Created as a conversation reply; human approval required before delivery.")
                result = dict(draft)
                for key in ("id","prospect_id","campaign_id"):
                    result[key] = str(result[key])
                return result
