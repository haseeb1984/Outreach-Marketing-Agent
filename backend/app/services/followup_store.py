"""Timed campaign follow-ups; creates drafts for human approval and never sends."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from uuid import UUID


class FollowupStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create_sequence(self, *, workspace_id: str, campaign_id: UUID, actor_id: UUID | str,
                              name: str, channel: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        if channel not in {"email", "whatsapp"} or not 1 <= len(steps) <= 10:
            raise ValueError("followup_sequence_invalid")
        normalized = []
        for index, step in enumerate(steps, 1):
            delay = step.get("delay_minutes")
            subject = step.get("subject_template")
            body = step.get("body_template")
            if isinstance(delay, bool) or not isinstance(delay, int) or not 0 <= delay <= 43200:
                raise ValueError("followup_delay_invalid")
            if not isinstance(body, str) or not body.strip() or len(body.strip()) > 10000:
                raise ValueError("followup_body_invalid")
            if subject is not None and (not isinstance(subject, str) or len(subject) > 300):
                raise ValueError("followup_subject_invalid")
            if channel == "email" and not (subject or "").strip():
                raise ValueError("followup_email_subject_required")
            normalized.append((index, delay, subject.strip() if isinstance(subject, str) else None, body.strip()))
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                campaign = await conn.fetchrow(
                    "SELECT status FROM outreach_campaigns WHERE id=$1 AND workspace_id=$2 FOR UPDATE",
                    campaign_id, workspace_id,
                )
                if campaign is None:
                    raise LookupError("campaign_not_found")
                row = await conn.fetchrow(
                    """INSERT INTO outreach_followup_sequences
                       (workspace_id,campaign_id,name,channel,created_by)
                       VALUES($1,$2,$3,$4,$5)
                       RETURNING id,workspace_id,campaign_id,name,channel,status,created_at,updated_at""",
                    workspace_id, campaign_id, name.strip(), channel, UUID(str(actor_id)),
                )
                for number, delay, subject, body in normalized:
                    await conn.execute(
                        """INSERT INTO outreach_followup_steps
                           (sequence_id,step_number,delay_minutes,subject_template,body_template)
                           VALUES($1,$2,$3,$4,$5)""",
                        row["id"], number, delay, subject, body,
                    )
                result = dict(row)
                result["steps"] = [{"step_number": n, "delay_minutes": d, "subject_template": s,
                                    "body_template": b} for n, d, s, b in normalized]
                return self._serialize(result)

    async def list_sequences(self, *, workspace_id: str, campaign_id: UUID | None = None) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT s.id,s.workspace_id,s.campaign_id,s.name,s.channel,s.status,s.created_at,s.updated_at,
                          count(DISTINCT e.id)::int AS enrollment_count,
                          count(DISTINCT e.id) FILTER (WHERE e.status='active')::int AS active_count,
                          count(DISTINCT e.id) FILTER (WHERE e.status='awaiting_approval')::int AS awaiting_approval_count
                   FROM outreach_followup_sequences s
                   LEFT JOIN outreach_followup_enrollments e ON e.sequence_id=s.id AND e.workspace_id=s.workspace_id
                   WHERE s.workspace_id=$1 AND ($2::uuid IS NULL OR s.campaign_id=$2)
                   GROUP BY s.id ORDER BY s.created_at DESC""",
                workspace_id, campaign_id,
            )
            return [self._serialize(dict(row)) for row in rows]

    async def set_sequence_status(self, *, workspace_id: str, sequence_id: UUID, status: str) -> dict[str, Any] | None:
        if status not in {"draft", "active", "paused", "archived"}:
            raise ValueError("followup_sequence_status_invalid")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """UPDATE outreach_followup_sequences SET status=$3,updated_at=now()
                       WHERE id=$1 AND workspace_id=$2 RETURNING id,status""",
                    sequence_id, workspace_id, status,
                )
                if row is None:
                    return None
                if status == "paused":
                    await conn.execute(
                        """UPDATE outreach_followup_enrollments
                           SET status='paused',pause_reason='sequence_paused',paused_next_run_at=next_run_at,next_run_at=NULL,updated_at=now()
                           WHERE sequence_id=$1 AND workspace_id=$2 AND status='active'""",
                        sequence_id, workspace_id,
                    )
                elif status == "active":
                    await conn.execute(
                        """UPDATE outreach_followup_enrollments
                           SET status='active',next_run_at=COALESCE(paused_next_run_at,now()),
                               paused_next_run_at=NULL,pause_reason=NULL,updated_at=now()
                           WHERE sequence_id=$1 AND workspace_id=$2 AND status='paused' AND pause_reason='sequence_paused'""",
                        sequence_id, workspace_id,
                    )
                elif status == "archived":
                    await conn.execute(
                        """UPDATE outreach_followup_enrollments SET status='archived',next_run_at=NULL,
                           paused_next_run_at=NULL,pause_reason=NULL,updated_at=now()
                           WHERE sequence_id=$1 AND workspace_id=$2 AND status IN ('active','paused')""",
                        sequence_id, workspace_id,
                    )
                return {"id": str(row["id"]), "status": row["status"]}

    async def enroll(self, *, workspace_id: str, sequence_id: UUID, prospect_id: UUID,
                     actor_id: UUID | str) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """SELECT s.status,s.channel,c.status AS campaign_status,p.stage,p.archived_at
                       FROM outreach_followup_sequences s
                       JOIN outreach_campaigns c ON c.id=s.campaign_id AND c.workspace_id=s.workspace_id
                       JOIN crm_prospects p ON p.workspace_id=s.workspace_id AND p.id=$3
                       WHERE s.id=$1 AND s.workspace_id=$2 FOR UPDATE OF s,p""",
                    sequence_id, workspace_id, prospect_id,
                )
                if row is None:
                    raise LookupError("followup_target_not_found")
                if row["status"] != "active" or row["campaign_status"] != "active":
                    raise ValueError("followup_sequence_or_campaign_not_active")
                if row["archived_at"] is not None or row["stage"] in {"replied", "do_not_contact"}:
                    raise ValueError("followup_prospect_ineligible")
                first = await conn.fetchval(
                    "SELECT delay_minutes FROM outreach_followup_steps WHERE sequence_id=$1 AND step_number=1",
                    sequence_id,
                )
                if first is None:
                    raise ValueError("followup_sequence_has_no_steps")
                created = await conn.fetchrow(
                    """INSERT INTO outreach_followup_enrollments
                       (workspace_id,sequence_id,prospect_id,created_by,next_run_at)
                       VALUES($1,$2,$3,$4,now()+($5 * interval '1 minute'))
                       ON CONFLICT(sequence_id,prospect_id) DO NOTHING
                       RETURNING id,status,current_step,next_run_at""",
                    workspace_id, sequence_id, prospect_id, UUID(str(actor_id)), first,
                )
                if created is None:
                    raise ValueError("prospect_already_enrolled")
                return self._serialize(dict(created))

    async def process_due(self, *, limit: int = 50) -> dict[str, int]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("followup_batch_limit_invalid")
        created = stopped = skipped = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                due = await conn.fetch(
                    """SELECT e.id,e.workspace_id,e.sequence_id,e.prospect_id,e.created_by,e.current_step,
                              s.channel,s.campaign_id,c.client_business,c.client_offer,c.status AS campaign_status,
                              p.name AS prospect_name,p.company AS prospect_company,p.evidence_url,p.verified_facts,
                              p.stage,p.archived_at,p.contact_email,p.contact_phone_e164,
                              cc.email_suppressed,cc.whatsapp_opt_in_at,cc.whatsapp_opt_in_evidence_url,
                              cc.whatsapp_account_id,st.subject_template,st.body_template
                       FROM outreach_followup_enrollments e
                       JOIN outreach_followup_sequences s ON s.id=e.sequence_id AND s.workspace_id=e.workspace_id
                       JOIN outreach_campaigns c ON c.id=s.campaign_id AND c.workspace_id=s.workspace_id
                       JOIN crm_prospects p ON p.id=e.prospect_id AND p.workspace_id=e.workspace_id
                       JOIN outreach_followup_steps st ON st.sequence_id=e.sequence_id AND st.step_number=e.current_step
                       LEFT JOIN outreach_contact_controls cc ON cc.workspace_id=e.workspace_id AND cc.prospect_id=e.prospect_id
                       WHERE e.status='active' AND e.next_run_at <= now()
                         AND s.status='active' AND c.status='active'
                       ORDER BY e.next_run_at,e.id
                       FOR UPDATE OF e SKIP LOCKED LIMIT $1""",
                    limit,
                )
                for row in due:
                    reason = None
                    if row["archived_at"] is not None:
                        reason = "prospect_archived"
                    elif row["stage"] == "replied":
                        reason = "prospect_replied"
                    elif row["stage"] in {"do_not_contact", "disqualified", "converted"}:
                        reason = "prospect_suppressed" if row["stage"] == "do_not_contact" else "prospect_no_longer_eligible"
                    elif not isinstance(row["evidence_url"], str) or not row["evidence_url"].lower().startswith("https://"):
                        reason = "verified_source_evidence_required"
                    elif row["channel"] == "email" and (not row["contact_email"] or row["email_suppressed"]):
                        reason = "email_contact_ineligible"
                    elif row["channel"] == "whatsapp" and (
                        not row["contact_phone_e164"] or not row["whatsapp_opt_in_at"]
                        or not row["whatsapp_opt_in_evidence_url"] or not row["whatsapp_account_id"]
                    ):
                        reason = "whatsapp_consent_ineligible"
                    if reason:
                        await conn.execute(
                            """UPDATE outreach_followup_enrollments SET status=$2,last_error_code=$3,
                               next_run_at=NULL,updated_at=now() WHERE id=$1""",
                            row["id"], "stopped_replied" if reason == "prospect_replied" else
                            "stopped_opt_out" if reason in {"prospect_suppressed","email_contact_ineligible","whatsapp_consent_ineligible"} else
                            "stopped_ineligible", reason,
                        )
                        stopped += 1
                        continue
                    if row["channel"] == "whatsapp":
                        active_account = await conn.fetchval(
                            """SELECT EXISTS(SELECT 1 FROM workspace_whatsapp_accounts
                               WHERE id=$1 AND workspace_id=$2 AND status='active')""",
                            row["whatsapp_account_id"], row["workspace_id"],
                        )
                        opted_out = await conn.fetchval(
                            """SELECT EXISTS(SELECT 1 FROM whatsapp_contact_preferences
                               WHERE workspace_id=$1 AND wa_id=$2 AND opted_out_at IS NOT NULL
                                 AND (opted_in_at IS NULL OR opted_out_at >= opted_in_at))""",
                            row["workspace_id"], "".join(ch for ch in str(row["contact_phone_e164"]) if ch.isdigit()),
                        )
                        if not active_account or opted_out:
                            await conn.execute(
                                """UPDATE outreach_followup_enrollments SET status='stopped_opt_out',
                                   last_error_code=$2,next_run_at=NULL,updated_at=now() WHERE id=$1""",
                                row["id"], "whatsapp_account_or_consent_inactive",
                            )
                            stopped += 1
                            continue
                    pending = await conn.fetchval(
                        """SELECT EXISTS(SELECT 1 FROM outreach_drafts WHERE workspace_id=$1
                           AND campaign_id=$2 AND prospect_id=$3 AND channel=$4 AND status='pending_approval')""",
                        row["workspace_id"], row["campaign_id"], row["prospect_id"], row["channel"],
                    )
                    if pending:
                        await conn.execute(
                            """UPDATE outreach_followup_enrollments SET status='paused',pause_reason='pending_draft_conflict',
                               last_error_code='existing_pending_draft_requires_review',next_run_at=NULL,updated_at=now()
                               WHERE id=$1""", row["id"],
                        )
                        skipped += 1
                        continue
                    name = (row["prospect_name"] or "").strip()
                    first_name = name.split(" ", 1)[0] if name else "there"
                    replacements = {
                        "{{first_name}}": first_name,
                        "{{company}}": str(row["prospect_company"] or ""),
                        "{{business}}": str(row["client_business"] or ""),
                        "{{offer}}": str(row["client_offer"] or ""),
                    }
                    body = str(row["body_template"])
                    subject = row["subject_template"]
                    for token, value in replacements.items():
                        body = body.replace(token, value)
                        if subject:
                            subject = subject.replace(token, value)
                    facts = row["verified_facts"] or []
                    if isinstance(facts, str):
                        try:
                            facts = json.loads(facts)
                        except (TypeError, ValueError):
                            facts = []
                    if not isinstance(facts, list):
                        facts = []
                    draft = await conn.fetchrow(
                        """INSERT INTO outreach_drafts
                           (workspace_id,campaign_id,prospect_id,channel,subject,body,source_evidence_url,
                            verified_facts_used,status,created_by)
                           VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,'pending_approval',$9)
                           ON CONFLICT DO NOTHING RETURNING id""",
                        row["workspace_id"], row["campaign_id"], row["prospect_id"], row["channel"],
                        subject, body, row["evidence_url"], json.dumps(facts), row["created_by"],
                    )
                    if draft is None:
                        await conn.execute(
                            """UPDATE outreach_followup_enrollments SET status='paused',pause_reason='pending_draft_conflict',
                               last_error_code='existing_pending_draft_requires_review',next_run_at=NULL,updated_at=now()
                               WHERE id=$1""", row["id"],
                        )
                        skipped += 1
                        continue
                    await conn.execute(
                        """INSERT INTO outreach_draft_events(draft_id,workspace_id,actor_id,event_type,note)
                           VALUES($1,$2,$3,'created',$4)""",
                        draft["id"], row["workspace_id"], row["created_by"],
                        f"Created from follow-up sequence step {row['current_step']}; approval required.",
                    )
                    await conn.execute(
                        """UPDATE outreach_followup_enrollments SET status='awaiting_approval',
                           current_draft_id=$2,last_error_code=NULL,next_run_at=NULL,updated_at=now()
                           WHERE id=$1""",
                        row["id"], draft["id"],
                    )
                    created += 1
        return {"drafts_created": created, "stopped": stopped, "skipped": skipped}

    async def list_enrollments(self, *, workspace_id: str, sequence_id: UUID, limit: int = 100,
                            offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200 or not 0 <= offset <= 100000:
            raise ValueError("pagination_out_of_range")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT e.id,e.workspace_id,e.sequence_id,e.prospect_id,e.current_step,e.status,
                          e.next_run_at,e.paused_next_run_at,e.pause_reason,e.current_draft_id,e.last_delivery_id,
                          e.last_whatsapp_delivery_id,e.last_error_code,e.created_at,e.updated_at,p.name AS prospect_name,p.company
                   FROM outreach_followup_enrollments e
                   JOIN crm_prospects p ON p.id=e.prospect_id AND p.workspace_id=e.workspace_id
                   WHERE e.workspace_id=$1 AND e.sequence_id=$2
                   ORDER BY e.created_at DESC,e.id LIMIT $3 OFFSET $4""",
                workspace_id, sequence_id, limit, offset,
            )
            return [self._serialize(dict(row)) for row in rows]

    async def set_enrollment_status(self, *, workspace_id: str, enrollment_id: UUID,
                                    status: str) -> dict[str, Any] | None:
        if status not in {"active", "paused", "archived"}:
            raise ValueError("followup_enrollment_status_invalid")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if status == "paused":
                    row = await conn.fetchrow(
                        """UPDATE outreach_followup_enrollments SET status='paused',pause_reason='operator_paused',
                           paused_next_run_at=next_run_at,next_run_at=NULL,updated_at=now()
                           WHERE id=$1 AND workspace_id=$2 AND status IN ('active','awaiting_approval')
                           RETURNING id,status,current_draft_id""",
                        enrollment_id, workspace_id,
                    )
                elif status == "active":
                    row = await conn.fetchrow(
                        """UPDATE outreach_followup_enrollments SET
                           status=CASE WHEN current_draft_id IS NOT NULL THEN 'awaiting_approval' ELSE 'active' END,
                           next_run_at=CASE WHEN current_draft_id IS NOT NULL THEN NULL
                                            ELSE COALESCE(paused_next_run_at,now()) END,
                           paused_next_run_at=NULL,pause_reason=NULL,updated_at=now()
                           WHERE id=$1 AND workspace_id=$2 AND status='paused'
                             AND pause_reason IN ('operator_paused','pending_draft_conflict')
                             AND (pause_reason <> 'pending_draft_conflict' OR (
                               current_draft_id IS NULL AND NOT EXISTS (
                                 SELECT 1 FROM outreach_followup_sequences s
                                 JOIN outreach_drafts d ON d.workspace_id=s.workspace_id
                                   AND d.campaign_id=s.campaign_id
                                   AND d.prospect_id=outreach_followup_enrollments.prospect_id
                                   AND d.channel=s.channel AND d.status='pending_approval'
                                 WHERE s.id=outreach_followup_enrollments.sequence_id
                               )
                             ))
                           RETURNING id,status,current_draft_id""",
                        enrollment_id, workspace_id,
                    )
                else:
                    row = await conn.fetchrow(
                        """UPDATE outreach_followup_enrollments SET status='archived',
                           next_run_at=NULL,paused_next_run_at=NULL,pause_reason=NULL,updated_at=now()
                           WHERE id=$1 AND workspace_id=$2 AND status NOT IN ('completed','stopped_replied',
                             'stopped_opt_out','stopped_ineligible','stopped_rejected','archived')
                           RETURNING id,status,current_draft_id""",
                        enrollment_id, workspace_id,
                    )
                return self._serialize(dict(row)) if row else None

    async def pause_for_draft(self, *, workspace_id: str, draft_id: UUID, reason: str) -> bool:
        safe_reason = reason[:100] if isinstance(reason, str) and reason else "followup_delivery_requires_review"
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE outreach_followup_enrollments SET status='paused',pause_reason='delivery_failed',
                   last_error_code=$3,next_run_at=NULL,updated_at=now()
                   WHERE workspace_id=$1 AND current_draft_id=$2 AND status='awaiting_approval'""",
                workspace_id, draft_id, safe_reason,
            )
        return result.endswith(" 1")

    async def advance_after_delivery(self, *, workspace_id: str, draft_id: UUID, delivery_id: UUID,
                                    channel: str = "email") -> bool:
        if channel not in {"email", "whatsapp"}:
            raise ValueError("followup_delivery_channel_invalid")
        delivery_column = "last_whatsapp_delivery_id" if channel == "whatsapp" else "last_delivery_id"
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                enrollment = await conn.fetchrow(
                    """SELECT e.id,e.sequence_id,e.current_step
                       FROM outreach_followup_enrollments e
                       WHERE e.workspace_id=$1 AND e.current_draft_id=$2
                         AND e.status='awaiting_approval' FOR UPDATE""",
                    workspace_id, draft_id,
                )
                if enrollment is None:
                    return False
                next_step = enrollment["current_step"] + 1
                delay = await conn.fetchval(
                    "SELECT delay_minutes FROM outreach_followup_steps WHERE sequence_id=$1 AND step_number=$2",
                    enrollment["sequence_id"], next_step,
                )
                if delay is None:
                    await conn.execute(
                        f"""UPDATE outreach_followup_enrollments SET status='completed',current_draft_id=NULL,
                           {delivery_column}=$2,next_run_at=NULL,updated_at=now() WHERE id=$1""",
                        enrollment["id"], delivery_id,
                    )
                else:
                    await conn.execute(
                        f"""UPDATE outreach_followup_enrollments SET status='active',current_step=$2,
                           current_draft_id=NULL,{delivery_column}=$3,
                           next_run_at=now()+($4 * interval '1 minute'),updated_at=now() WHERE id=$1""",
                        enrollment["id"], next_step, delivery_id, delay,
                    )
                return True

    async def resolve_delivery(
        self, *, workspace_id: str, enrollment_id: UUID, delivery_id: UUID,
        outcome: str, actor_id: UUID | str, reason: str, evidence_url: str,
    ) -> dict[str, Any] | None:
        """Record an admin's reviewed provider outcome; never retries a delivery."""
        if outcome not in {"delivered", "not_delivered"}:
            raise ValueError("followup_resolution_outcome_invalid")
        if not isinstance(reason, str) or not 12 <= len(reason.strip()) <= 2000:
            raise ValueError("followup_resolution_reason_invalid")
        if not isinstance(evidence_url, str) or not evidence_url.startswith("https://") or len(evidence_url) > 2048:
            raise ValueError("followup_resolution_evidence_invalid")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                enrollment = await conn.fetchrow(
                    """SELECT e.id,e.sequence_id,e.current_step,e.current_draft_id,e.pause_reason,
                              s.channel
                       FROM outreach_followup_enrollments e
                       JOIN outreach_followup_sequences s
                         ON s.id=e.sequence_id AND s.workspace_id=e.workspace_id
                       WHERE e.id=$1 AND e.workspace_id=$2
                         AND e.status='paused'
                         AND e.pause_reason IN ('delivery_failed','delivery_uncertain')
                       FOR UPDATE OF e""",
                    enrollment_id, workspace_id,
                )
                if enrollment is None or enrollment["current_draft_id"] is None:
                    return None
                if enrollment["channel"] == "email":
                    delivery = await conn.fetchrow(
                        """SELECT id,draft_id,status,provider_status FROM outreach_deliveries
                           WHERE id=$1 AND workspace_id=$2 AND draft_id=$3 AND channel='email'
                           FOR UPDATE""",
                        delivery_id, workspace_id, enrollment["current_draft_id"],
                    )
                    if delivery is None or delivery["status"] not in {"failed", "uncertain"}:
                        raise ValueError("followup_delivery_not_recoverable")
                    provider_status = delivery["provider_status"]
                else:
                    delivery = await conn.fetchrow(
                        """SELECT id,draft_id,status FROM whatsapp_outbound_deliveries
                           WHERE id=$1 AND workspace_id=$2 AND draft_id=$3
                           FOR UPDATE""",
                        delivery_id, workspace_id, enrollment["current_draft_id"],
                    )
                    if delivery is None or delivery["status"] not in {"failed", "uncertain", "delivered", "read"}:
                        raise ValueError("followup_delivery_not_recoverable")
                    provider_status = delivery["status"]
                if outcome == "delivered":
                    if enrollment["channel"] == "email" and provider_status != "delivered":
                        raise ValueError("provider_delivery_confirmation_required")
                    if enrollment["channel"] == "whatsapp" and provider_status not in {"delivered", "read"}:
                        raise ValueError("provider_delivery_confirmation_required")
                    next_step = enrollment["current_step"] + 1
                    delay = await conn.fetchval(
                        "SELECT delay_minutes FROM outreach_followup_steps WHERE sequence_id=$1 AND step_number=$2",
                        enrollment["sequence_id"], next_step,
                    )
                    if delay is None:
                        await conn.execute(
                            """UPDATE outreach_followup_enrollments SET status='completed',
                               current_draft_id=NULL,last_delivery_id=CASE WHEN $2='email' THEN $3 ELSE last_delivery_id END,
                               last_whatsapp_delivery_id=CASE WHEN $2='whatsapp' THEN $3 ELSE last_whatsapp_delivery_id END,
                               next_run_at=NULL,paused_next_run_at=NULL,pause_reason=NULL,last_error_code=NULL,updated_at=now()
                               WHERE id=$1""",
                            enrollment_id, enrollment["channel"], delivery_id,
                        )
                        next_status = "completed"
                    else:
                        await conn.execute(
                            """UPDATE outreach_followup_enrollments SET status='active',current_step=$2,
                               current_draft_id=NULL,last_delivery_id=CASE WHEN $3='email' THEN $4 ELSE last_delivery_id END,
                               last_whatsapp_delivery_id=CASE WHEN $3='whatsapp' THEN $4 ELSE last_whatsapp_delivery_id END,
                               next_run_at=now()+($5 * interval '1 minute'),paused_next_run_at=NULL,
                               pause_reason=NULL,last_error_code=NULL,updated_at=now() WHERE id=$1""",
                            enrollment_id, next_step, enrollment["channel"], delivery_id, delay,
                        )
                        next_status = "active"
                else:
                    await conn.execute(
                        """UPDATE outreach_followup_enrollments SET status='stopped_ineligible',
                           current_draft_id=NULL,next_run_at=NULL,paused_next_run_at=NULL,pause_reason=NULL,
                           last_error_code='admin_confirmed_not_delivered',updated_at=now()
                           WHERE id=$1""",
                        enrollment_id,
                    )
                    next_status = "stopped_ineligible"
                await conn.execute(
                    """INSERT INTO outreach_followup_delivery_resolutions
                       (workspace_id,enrollment_id,draft_id,delivery_id,channel,outcome,provider_status,
                        reason,evidence_url,resolved_by)
                       VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                    workspace_id, enrollment_id, enrollment["current_draft_id"], delivery_id,
                    enrollment["channel"], outcome, provider_status, reason.strip(), evidence_url,
                    UUID(str(actor_id)),
                )
                return {"id": str(enrollment_id), "status": next_status, "outcome": outcome}

    async def reject_draft(self, *, workspace_id: str, draft_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE outreach_followup_enrollments SET status='stopped_rejected',
                   current_draft_id=NULL,next_run_at=NULL,last_error_code='followup_draft_rejected',updated_at=now()
                   WHERE workspace_id=$1 AND current_draft_id=$2 AND status='awaiting_approval'""",
                workspace_id, draft_id,
            )

    @staticmethod
    def _serialize(row: dict[str, Any]) -> dict[str, Any]:
        for key in ("id", "workspace_id", "campaign_id", "prospect_id", "created_by",
                    "current_draft_id", "last_delivery_id", "last_whatsapp_delivery_id", "sequence_id"):
            if row.get(key) is not None:
                row[key] = str(row[key])
        for key in ("created_at", "updated_at", "next_run_at", "paused_next_run_at"):
            if row.get(key) is not None and isinstance(row[key], datetime):
                row[key] = row[key].astimezone(timezone.utc).isoformat()
        return row
