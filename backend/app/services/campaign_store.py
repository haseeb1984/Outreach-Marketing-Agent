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

    async def update_campaign(self, *, workspace_id: str, campaign_id: UUID, name: str, client_business: str, client_offer: str, target_customer_profile: str, status: str) -> dict[str, Any] | None:
        if status not in {"draft", "active", "paused", "archived"}:
            raise ValueError("invalid_campaign_status")
        fields = ((name, 200), (client_business, 240), (client_offer, 2000), (target_customer_profile, 2000))
        if any(not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum for value, maximum in fields):
            raise ValueError("invalid_campaign_fields")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE outreach_campaigns SET name=$3,client_business=$4,client_offer=$5,
                   target_customer_profile=$6,status=$7,updated_at=now()
                   WHERE id=$1 AND workspace_id=$2
                   RETURNING id,workspace_id,name,client_business,client_offer,target_customer_profile,
                             status,created_by,created_at,updated_at""",
                campaign_id, workspace_id, name.strip(), client_business.strip(),
                client_offer.strip(), target_customer_profile.strip(), status,
            )
        return self._serialize(dict(row)) if row else None

    async def create_draft(self, *, workspace_id: str, campaign_id: UUID, prospect_id: UUID,
                           actor_id: UUID | str, channel: str, call_to_action: str,
                           ) -> dict[str, Any] | None:
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
                if p.get("stage") == "do_not_contact":
                    raise ValueError("contact_suppressed")
                controls = await conn.fetchrow("SELECT * FROM outreach_contact_controls WHERE workspace_id=$1 AND prospect_id=$2", workspace_id, prospect_id)
                if channel == "email":
                    if not p.get("contact_email"):
                        raise ValueError("prospect_email_required")
                    if controls and controls["email_suppressed"]:
                        raise ValueError("contact_suppressed")
                if channel == "whatsapp":
                    if not controls or controls["whatsapp_opt_in_at"] is None or not controls["whatsapp_opt_in_evidence_url"]:
                        raise ValueError("WhatsApp documented opt-in evidence is required")
                    phone_digits = "".join(ch for ch in str(p.get("contact_phone_e164") or "") if ch.isdigit())
                    if not phone_digits:
                        raise ValueError("prospect_whatsapp_phone_required")
                    opted_out = await conn.fetchval(
                        """SELECT EXISTS(
                             SELECT 1 FROM whatsapp_contact_preferences
                             WHERE workspace_id=$1 AND wa_id=$2 AND opted_out_at IS NOT NULL
                               AND (opted_in_at IS NULL OR opted_out_at >= opted_in_at)
                           )""",
                        workspace_id, phone_digits,
                    )
                    if opted_out:
                        raise ValueError("WhatsApp contact has opted out")
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
                    whatsapp_opt_in_confirmed=(channel != "whatsapp" or bool(controls and controls["whatsapp_opt_in_at"])),
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

    async def update_draft(
        self, *, workspace_id: str, draft_id: UUID, actor_id: UUID | str,
        subject: str | None, body: str,
    ) -> dict[str, Any] | None:
        """Edit content only while a draft is pending human approval."""
        cleaned_body = body.strip() if isinstance(body, str) else ""
        cleaned_subject = subject.strip() if isinstance(subject, str) else None
        if not cleaned_body or len(cleaned_body) > 10000:
            raise ValueError("draft_body_invalid")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    """SELECT channel,status FROM outreach_drafts
                       WHERE id=$1 AND workspace_id=$2 FOR UPDATE""",
                    draft_id, workspace_id,
                )
                if current is None:
                    return None
                if current["status"] != "pending_approval":
                    raise ValueError("draft_not_pending")
                if current["channel"] == "email" and not cleaned_subject:
                    raise ValueError("draft_subject_required")
                if current["channel"] == "whatsapp":
                    cleaned_subject = None
                row = await conn.fetchrow(
                    """UPDATE outreach_drafts SET subject=$3,body=$4,updated_at=now()
                       WHERE id=$1 AND workspace_id=$2 AND status='pending_approval'
                       RETURNING *""",
                    draft_id, workspace_id, cleaned_subject, cleaned_body,
                )
                if row is None:
                    raise ValueError("draft_not_pending")
                await conn.execute(
                    """INSERT INTO outreach_draft_events(draft_id,workspace_id,actor_id,event_type,note)
                       VALUES($1,$2,$3,'edited','Draft content edited before approval')""",
                    draft_id, workspace_id, UUID(str(actor_id)),
                )
        return self._serialize(dict(row))

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
        for key in ("id", "created_by", "reviewed_by", "campaign_id", "prospect_id", "updated_by"):
            if row.get(key) is not None:
                row[key] = str(row[key])
        if "verified_facts_used" in row:
            row["verified_facts_used"] = cls._json_list(row["verified_facts_used"])
        return row


    async def update_contact_controls(self, *, workspace_id: str, prospect_id: UUID, actor_id: UUID | str, email_suppressed: bool | None, whatsapp_opt_in_confirmed: bool, whatsapp_account_id: UUID | None, whatsapp_opt_in_evidence_url: str | None) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM crm_prospects WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL)", prospect_id, workspace_id)
                if not exists:
                    return None
                if whatsapp_opt_in_confirmed:
                    account_exists = await conn.fetchval(
                        """SELECT EXISTS(SELECT 1 FROM workspace_whatsapp_accounts
                           WHERE id=$1 AND workspace_id=$2 AND status='active')""",
                        whatsapp_account_id, workspace_id,
                    )
                    if not account_exists:
                        raise ValueError("whatsapp_account_not_active")
                row = await conn.fetchrow("""INSERT INTO outreach_contact_controls (workspace_id,prospect_id,email_suppressed,whatsapp_opt_in_at,whatsapp_opt_in_evidence_url,whatsapp_account_id,updated_by,updated_at) VALUES ($1,$2,COALESCE($3,FALSE),CASE WHEN $4 THEN now() ELSE NULL END,CASE WHEN $4 THEN $5 ELSE NULL END,CASE WHEN $4 THEN $6 ELSE NULL END,$7,now()) ON CONFLICT (workspace_id,prospect_id) DO UPDATE SET email_suppressed=COALESCE($3,outreach_contact_controls.email_suppressed),whatsapp_opt_in_at=CASE WHEN $4 THEN now() ELSE outreach_contact_controls.whatsapp_opt_in_at END,whatsapp_opt_in_evidence_url=CASE WHEN $4 THEN $5 ELSE outreach_contact_controls.whatsapp_opt_in_evidence_url END,whatsapp_account_id=CASE WHEN $4 THEN $6 ELSE outreach_contact_controls.whatsapp_account_id END,updated_by=$7,updated_at=now() RETURNING workspace_id,prospect_id,email_suppressed,whatsapp_opt_in_at,whatsapp_opt_in_evidence_url,whatsapp_account_id,updated_by,updated_at""", workspace_id, prospect_id, email_suppressed, whatsapp_opt_in_confirmed, whatsapp_opt_in_evidence_url, whatsapp_account_id, UUID(str(actor_id)))
                if whatsapp_opt_in_confirmed:
                    await conn.execute(
                        """UPDATE whatsapp_contact_preferences pref
                           SET opted_in_at=now(), updated_at=now()
                           FROM crm_prospects prospect
                           WHERE prospect.id=$1 AND prospect.workspace_id=$2
                             AND prospect.workspace_id=pref.workspace_id
                             AND pref.account_id=$3
                             AND pref.wa_id=regexp_replace(COALESCE(prospect.contact_phone_e164,''), '[^0-9]', '', 'g')
                             AND pref.opted_out_at IS NOT NULL""",
                        prospect_id, workspace_id, whatsapp_account_id,
                    )
        return self._serialize(dict(row))
