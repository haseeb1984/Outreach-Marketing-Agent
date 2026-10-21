"""Workspace-scoped outbound queue and send-time policy checks."""
from __future__ import annotations
from typing import Any
from uuid import UUID

class DeliveryStore:
    def __init__(self,pool: Any)->None: self._pool=pool

    async def enqueue(self,*,workspace_id: str,draft_id: UUID,actor_id: UUID|str,idempotency_key: str)->dict[str,Any]:
        async with self._pool.acquire() as c:
            async with c.transaction():
                d=await c.fetchrow("""SELECT d.id,d.status,d.channel,p.contact_email,cc.email_suppressed
                  FROM outreach_drafts d JOIN crm_prospects p ON p.id=d.prospect_id AND p.workspace_id=d.workspace_id
                  LEFT JOIN outreach_contact_controls cc ON cc.workspace_id=d.workspace_id AND cc.prospect_id=d.prospect_id
                  WHERE d.id=$1 AND d.workspace_id=$2 AND p.archived_at IS NULL FOR UPDATE OF d""",draft_id,workspace_id)
                if d is None: raise LookupError("draft_not_found")
                if d["status"]!="approved": raise ValueError("draft_not_approved")
                if d["channel"]!="email": raise ValueError("provider_channel_not_configured")
                if not d["contact_email"]: raise ValueError("prospect_email_required")
                if d["email_suppressed"]: raise ValueError("contact_suppressed")
                r=await c.fetchrow("""INSERT INTO outreach_deliveries(workspace_id,draft_id,channel,idempotency_key,queued_by)
                  VALUES($1,$2,'email',$3,$4) ON CONFLICT DO NOTHING RETURNING *""",workspace_id,draft_id,idempotency_key,UUID(str(actor_id)))
                if r is None:
                    r=await c.fetchrow("""SELECT * FROM outreach_deliveries WHERE workspace_id=$1
                      AND (idempotency_key=$2 OR draft_id=$3) ORDER BY (idempotency_key=$2) DESC LIMIT 1 FOR UPDATE""",workspace_id,idempotency_key,draft_id)
                    if r is None or r["draft_id"]!=draft_id: raise ValueError("idempotency_key_conflict")
                return self._serialize(dict(r))

    async def list_deliveries(self,*,workspace_id: str,limit: int=50,offset: int=0)->list[dict[str,Any]]:
        if not 1<=limit<=100 or not 0<=offset<=100000: raise ValueError("pagination_out_of_range")
        async with self._pool.acquire() as c:
            rows=await c.fetch("SELECT * FROM outreach_deliveries WHERE workspace_id=$1 ORDER BY queued_at DESC,id LIMIT $2 OFFSET $3",workspace_id,limit,offset)
        return [self._serialize(dict(r)) for r in rows]

    async def claim(self,*,workspace_id: str,delivery_id: UUID)->dict[str,Any]:
        async with self._pool.acquire() as c:
            async with c.transaction():
                r=await c.fetchrow("""SELECT q.status AS queue_status,d.status AS draft_status,d.channel,d.subject,d.body,
                  p.contact_email,cc.email_suppressed FROM outreach_deliveries q
                  JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                  JOIN crm_prospects p ON p.id=d.prospect_id AND p.workspace_id=d.workspace_id
                  LEFT JOIN outreach_contact_controls cc ON cc.workspace_id=d.workspace_id AND cc.prospect_id=d.prospect_id
                  WHERE q.id=$1 AND q.workspace_id=$2 FOR UPDATE OF q,d""",delivery_id,workspace_id)
                if r is None: raise LookupError("delivery_not_found")
                if r["queue_status"]!="queued": raise ValueError("delivery_not_queued")
                if r["draft_status"]!="approved": raise ValueError("draft_not_approved")
                if r["channel"]!="email": raise ValueError("provider_channel_not_configured")
                if not r["contact_email"]: raise ValueError("prospect_email_required")
                if r["email_suppressed"]: raise ValueError("contact_suppressed")
                await c.execute("""UPDATE outreach_deliveries SET status='processing',attempt_count=attempt_count+1,
                  processing_at=now(),updated_at=now() WHERE id=$1 AND workspace_id=$2 AND status='queued'""",delivery_id,workspace_id)
                return {"recipient":r["contact_email"],"subject":r["subject"] or "A message from a business","body":r["body"]}

    async def finish(self,*,workspace_id: str,delivery_id: UUID,error_code: str|None=None)->bool:
        async with self._pool.acquire() as c:
            if error_code is None:
                result=await c.execute("""UPDATE outreach_deliveries SET status='sent',sent_at=now(),updated_at=now()
                  WHERE id=$1 AND workspace_id=$2 AND status='processing'""",delivery_id,workspace_id)
            else:
                result=await c.execute("""UPDATE outreach_deliveries SET status='failed',error_code=$3,updated_at=now()
                  WHERE id=$1 AND workspace_id=$2 AND status='processing'""",delivery_id,workspace_id,error_code[:100])
        return result.endswith(" 1")

    @staticmethod
    def _serialize(r: dict[str,Any])->dict[str,Any]:
        for k in ("id","draft_id","queued_by"):
            if r.get(k) is not None: r[k]=str(r[k])
        return r
