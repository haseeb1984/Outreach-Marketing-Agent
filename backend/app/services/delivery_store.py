"""Workspace-scoped outbound queue and send-time policy checks."""
from __future__ import annotations
from typing import Any
from uuid import UUID

class DeliveryStore:
    def __init__(self,pool: Any)->None: self._pool=pool

    async def enqueue(self,*,workspace_id: str,draft_id: UUID,actor_id: UUID|str,idempotency_key: str,email_account_id: UUID|None=None)->dict[str,Any]:
        async with self._pool.acquire() as c:
            async with c.transaction():
                d=await c.fetchrow("""SELECT d.id,d.status,d.channel,p.contact_email,p.stage,cc.email_suppressed,c.status AS campaign_status
                  FROM outreach_drafts d JOIN outreach_campaigns c ON c.id=d.campaign_id AND c.workspace_id=d.workspace_id
                  JOIN crm_prospects p ON p.id=d.prospect_id AND p.workspace_id=d.workspace_id
                  LEFT JOIN outreach_contact_controls cc ON cc.workspace_id=d.workspace_id AND cc.prospect_id=d.prospect_id
                  WHERE d.id=$1 AND d.workspace_id=$2 AND p.archived_at IS NULL FOR UPDATE OF d""",draft_id,workspace_id)
                if d is None: raise LookupError("draft_not_found")
                if d["status"]!="approved": raise ValueError("draft_not_approved")
                if d["campaign_status"] == "archived": raise ValueError("campaign_archived")
                if d["channel"]!="email": raise ValueError("provider_channel_not_configured")
                if not d["contact_email"]: raise ValueError("prospect_email_required")
                if d["email_suppressed"] or d["stage"] == "do_not_contact": raise ValueError("contact_suppressed")
                if email_account_id is not None:
                    account = await c.fetchrow("SELECT status FROM workspace_email_accounts WHERE id=$1 AND workspace_id=$2 FOR SHARE", email_account_id, workspace_id)
                    if account is None or account["status"] != "active": raise LookupError("email_account_not_available")
                r=await c.fetchrow("""INSERT INTO outreach_deliveries(workspace_id,draft_id,channel,idempotency_key,queued_by,email_account_id)
                  VALUES($1,$2,'email',$3,$4,$5) ON CONFLICT DO NOTHING RETURNING *""",workspace_id,draft_id,idempotency_key,UUID(str(actor_id)),email_account_id)
                if r is None:
                    r=await c.fetchrow("""SELECT * FROM outreach_deliveries WHERE workspace_id=$1
                      AND (idempotency_key=$2 OR draft_id=$3) ORDER BY (idempotency_key=$2) DESC LIMIT 1 FOR UPDATE""",workspace_id,idempotency_key,draft_id)
                    if r is None or r["draft_id"]!=draft_id: raise ValueError("idempotency_key_conflict")
                    if r["email_account_id"] != email_account_id: raise ValueError("email_account_conflict")
                return self._serialize(dict(r))

    async def list_deliveries(self,*,workspace_id: str,limit: int=50,offset: int=0)->list[dict[str,Any]]:
        if not 1<=limit<=100 or not 0<=offset<=100000: raise ValueError("pagination_out_of_range")
        async with self._pool.acquire() as c:
            rows=await c.fetch("SELECT * FROM outreach_deliveries WHERE workspace_id=$1 ORDER BY queued_at DESC,id LIMIT $2 OFFSET $3",workspace_id,limit,offset)
        return [self._serialize(dict(r)) for r in rows]

    async def claim(self,*,workspace_id: str,delivery_id: UUID)->dict[str,Any]:
        async with self._pool.acquire() as c:
            async with c.transaction():
                r=await c.fetchrow("""SELECT q.status AS queue_status,d.status AS draft_status,d.channel,d.subject,d.body,q.email_account_id,
                  p.contact_email,p.stage,cc.email_suppressed,c.status AS campaign_status FROM outreach_deliveries q
                  JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                  JOIN outreach_campaigns c ON c.id=d.campaign_id AND c.workspace_id=d.workspace_id
                  JOIN crm_prospects p ON p.id=d.prospect_id AND p.workspace_id=d.workspace_id
                  LEFT JOIN outreach_contact_controls cc ON cc.workspace_id=d.workspace_id AND cc.prospect_id=d.prospect_id
                  WHERE q.id=$1 AND q.workspace_id=$2 FOR UPDATE OF q,d""",delivery_id,workspace_id)
                if r is None: raise LookupError("delivery_not_found")
                if r["queue_status"]!="queued": raise ValueError("delivery_not_queued")
                if r["draft_status"]!="approved": raise ValueError("draft_not_approved")
                if r["campaign_status"] == "archived": raise ValueError("campaign_archived")
                if r["channel"]!="email": raise ValueError("provider_channel_not_configured")
                if not r["contact_email"]: raise ValueError("prospect_email_required")
                if r["email_suppressed"] or r["stage"] == "do_not_contact": raise ValueError("contact_suppressed")
                await c.execute("""UPDATE outreach_deliveries SET status='processing',attempt_count=attempt_count+1,
                  processing_at=now(),updated_at=now() WHERE id=$1 AND workspace_id=$2 AND status='queued'""",delivery_id,workspace_id)
                return {"recipient":r["contact_email"],"subject":r["subject"] or "A message from a business","body":r["body"],"email_account_id":str(r["email_account_id"]) if r["email_account_id"] else None}

    async def finish(self,*,workspace_id: str,delivery_id: UUID,error_code: str|None=None)->bool:
        async with self._pool.acquire() as c:
            if error_code is None:
                result=await c.execute("""UPDATE outreach_deliveries SET status='sent',sent_at=now(),updated_at=now()
                  WHERE id=$1 AND workspace_id=$2 AND status='processing'""",delivery_id,workspace_id)
            elif error_code == "delivery_outcome_unknown":
                # SMTP/network failures can happen after a provider accepted the message.
                # Keep this terminal and visible; blindly retrying could send duplicates.
                result=await c.execute("""UPDATE outreach_deliveries SET status='uncertain',error_code=$3,updated_at=now()
                  WHERE id=$1 AND workspace_id=$2 AND status='processing'""",delivery_id,workspace_id,error_code[:100])
            else:
                result=await c.execute("""UPDATE outreach_deliveries SET status='failed',error_code=$3,updated_at=now()
                  WHERE id=$1 AND workspace_id=$2 AND status='processing'""",delivery_id,workspace_id,error_code[:100])
        return result.endswith(" 1")

    async def reconcile_stale_processing(self, *, workspace_id: str, older_than_seconds: int = 900, limit: int = 100) -> int:
        """Move one workspace's abandoned sends to an operator-visible uncertain state.

        Never automatically requeue a timed-out send: the provider may have accepted it
        before the worker disappeared. A bounded tenant-scoped update avoids cross-workspace
        changes and a large table-wide lock.
        """
        if not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200:
            raise ValueError("workspace_id_invalid")
        if isinstance(older_than_seconds, bool) or not isinstance(older_than_seconds, int) or not 60 <= older_than_seconds <= 86400:
            raise ValueError("stale_processing_age_out_of_range")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("reconciliation_limit_out_of_range")
        async with self._pool.acquire() as c:
            result = await c.execute(
                """WITH stale AS (
                       SELECT id
                       FROM outreach_deliveries
                       WHERE workspace_id=$1
                         AND status='processing'
                         AND processing_at IS NOT NULL
                         AND processing_at < now() - ($2 * interval '1 second')
                       ORDER BY processing_at ASC, id
                       FOR UPDATE SKIP LOCKED
                       LIMIT $3
                   )
                   UPDATE outreach_deliveries AS q
                   SET status='uncertain',
                       error_code='worker_lost_outcome_unknown',
                       updated_at=now()
                   FROM stale
                   WHERE q.id=stale.id AND q.workspace_id=$1 AND q.status='processing'""",
                workspace_id,
                older_than_seconds,
                limit,
            )
        # asyncpg command tags end with the affected row count.
        try:
            return int(result.rsplit(" ", 1)[-1])
        except (AttributeError, ValueError):
            return 0

    @staticmethod
    def _serialize(r: dict[str,Any])->dict[str,Any]:
        for k in ("id","draft_id","queued_by","email_account_id"):
            if r.get(k) is not None: r[k]=str(r[k])
        return r
