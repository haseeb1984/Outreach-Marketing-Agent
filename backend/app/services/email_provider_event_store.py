"""Idempotent tenant-scoped processing of normalized email provider feedback."""
from __future__ import annotations

from typing import Any
from uuid import UUID


class EmailProviderEventStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def ingest(
        self, *, provider: str, event_id: str, delivery_id: UUID,
        event_type: str, occurred_at: Any, recipient: str,
    ) -> dict[str, Any]:
        if event_type not in {"delivered", "deferred", "bounced", "complained", "unsubscribed"}:
            raise ValueError("email_event_type_invalid")
        if not provider.strip() or len(provider) > 80 or not event_id.strip() or len(event_id) > 300:
            raise ValueError("email_event_identity_invalid")
        if not recipient.strip() or len(recipient) > 320:
            raise ValueError("email_event_recipient_invalid")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                delivery = await conn.fetchrow(
                    """SELECT q.id,q.draft_id,q.workspace_id,q.provider_status,q.provider_status_at,
                              p.id AS prospect_id,p.contact_email,p.created_by
                       FROM outreach_deliveries q
                       JOIN outreach_drafts d ON d.id=q.draft_id AND d.workspace_id=q.workspace_id
                       JOIN crm_prospects p ON p.id=d.prospect_id AND p.workspace_id=d.workspace_id
                       WHERE q.id=$1 AND q.channel='email'
                       FOR UPDATE OF q,p""",
                    delivery_id,
                )
                if delivery is None:
                    raise LookupError("email_delivery_not_found")
                if delivery["contact_email"] is None or delivery["contact_email"].strip().casefold() != recipient.strip().casefold():
                    raise ValueError("email_event_recipient_mismatch")

                inserted = await conn.fetchval(
                    """INSERT INTO email_provider_events
                       (provider,provider_event_id,delivery_id,event_type,occurred_at)
                       VALUES($1,$2,$3,$4,$5)
                       ON CONFLICT(provider,provider_event_id) DO NOTHING
                       RETURNING id""",
                    provider, event_id, delivery_id, event_type, occurred_at,
                )
                if inserted is None:
                    return {"duplicate": True, "event_id": event_id}

                # Preserve the newest provider state; older delayed callbacks remain in
                # the immutable ledger but cannot roll the visible state backwards.
                await conn.execute(
                    """UPDATE outreach_deliveries
                       SET provider_status=$2,provider_status_at=$3,updated_at=now()
                       WHERE id=$1 AND workspace_id=$4
                         AND (provider_status_at IS NULL OR provider_status_at <= $3)""",
                    delivery_id, event_type, occurred_at, delivery["workspace_id"],
                )

                if event_type == "delivered":
                    # A provider's signed delivered callback is authoritative. Advance the
                    # matching follow-up once; current_draft_id is the idempotency guard.
                    await conn.execute(
                        """WITH target AS (
                               SELECT e.id,e.sequence_id,e.current_step
                               FROM outreach_followup_enrollments e
                               WHERE e.workspace_id=$1 AND e.current_draft_id=$2
                                 AND e.status IN ('awaiting_approval','paused')
                                 AND (e.status='awaiting_approval' OR e.pause_reason IN ('delivery_failed','delivery_uncertain'))
                               FOR UPDATE
                           ), next_step AS (
                               SELECT t.id,t.current_step+1 AS step_number,
                                      st.delay_minutes
                               FROM target t
                               LEFT JOIN outreach_followup_steps st
                                 ON st.sequence_id=t.sequence_id AND st.step_number=t.current_step+1
                           )
                           UPDATE outreach_followup_enrollments e
                           SET status=CASE WHEN n.delay_minutes IS NULL THEN 'completed' ELSE 'active' END,
                               current_step=CASE WHEN n.delay_minutes IS NULL THEN e.current_step ELSE n.step_number END,
                               current_draft_id=NULL,last_delivery_id=$3,
                               next_run_at=CASE WHEN n.delay_minutes IS NULL THEN NULL
                                                ELSE now()+(n.delay_minutes * interval '1 minute') END,
                               paused_next_run_at=NULL,pause_reason=NULL,last_error_code=NULL,updated_at=now()
                           FROM next_step n WHERE e.id=n.id""",
                        delivery["workspace_id"], delivery["draft_id"], delivery_id,
                    )

                suppression_reason = {
                    "bounced": "hard_bounce",
                    "complained": "spam_complaint",
                    "unsubscribed": "unsubscribe",
                }.get(event_type)
                if suppression_reason:
                    await conn.execute(
                        """INSERT INTO outreach_contact_controls
                           (workspace_id,prospect_id,email_suppressed,email_suppression_reason,
                            email_suppressed_at,updated_by,updated_at)
                           VALUES($1,$2,TRUE,$3,$4,$5,now())
                           ON CONFLICT(workspace_id,prospect_id) DO UPDATE
                           SET email_suppressed=TRUE,
                               email_suppression_reason=EXCLUDED.email_suppression_reason,
                               email_suppressed_at=COALESCE(
                                   outreach_contact_controls.email_suppressed_at,EXCLUDED.email_suppressed_at
                               ),
                               updated_at=now()""",
                        delivery["workspace_id"], delivery["prospect_id"],
                        suppression_reason, occurred_at, delivery["created_by"],
                    )
                    # Suppression is terminal for every email follow-up in this workspace.
                    # Clear scheduling immediately; retain current_draft_id for operator traceability.
                    await conn.execute(
                        """UPDATE outreach_followup_enrollments e
                           SET status='stopped_opt_out',next_run_at=NULL,paused_next_run_at=NULL,
                               pause_reason=NULL,last_error_code=$3,updated_at=now()
                           FROM outreach_followup_sequences s
                           WHERE s.id=e.sequence_id AND s.workspace_id=e.workspace_id
                             AND e.workspace_id=$1 AND e.prospect_id=$2 AND s.channel='email'
                             AND e.status IN ('active','awaiting_approval','paused')""",
                        delivery["workspace_id"], delivery["prospect_id"],
                        "email_" + suppression_reason,
                    )
                    # Stop all queued email sends to this contact, not just this campaign.
                    await conn.execute(
                        """UPDATE outreach_deliveries q
                           SET status='cancelled',error_code=$3,updated_at=now()
                           FROM outreach_drafts d
                           WHERE q.workspace_id=$1 AND q.draft_id=d.id
                             AND d.workspace_id=q.workspace_id AND d.prospect_id=$2
                             AND q.channel='email' AND q.status='queued'""",
                        delivery["workspace_id"], delivery["prospect_id"],
                        "email_" + suppression_reason,
                    )

                return {
                    "duplicate": False,
                    "event_id": event_id,
                    "event_type": event_type,
                    "workspace_id": delivery["workspace_id"],
                    "prospect_id": str(delivery["prospect_id"]),
                    "suppressed": bool(suppression_reason),
                }

    async def unsubscribe(
        self, *, workspace_id: str, prospect_id: UUID, email: str, occurred_at: Any,
    ) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                prospect = await conn.fetchrow(
                    """SELECT id,contact_email,created_by FROM crm_prospects
                       WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL FOR UPDATE""",
                    prospect_id, workspace_id,
                )
                if prospect is None or not prospect["contact_email"] or prospect["contact_email"].strip().casefold() != email.casefold():
                    raise LookupError("unsubscribe_contact_not_found")
                await conn.execute(
                    """INSERT INTO outreach_contact_controls
                       (workspace_id,prospect_id,email_suppressed,email_suppression_reason,
                        email_suppressed_at,updated_by,updated_at)
                       VALUES($1,$2,TRUE,'unsubscribe',$3,$4,now())
                       ON CONFLICT(workspace_id,prospect_id) DO UPDATE
                       SET email_suppressed=TRUE,email_suppression_reason='unsubscribe',
                           email_suppressed_at=COALESCE(outreach_contact_controls.email_suppressed_at,EXCLUDED.email_suppressed_at),
                           updated_at=now()""",
                    workspace_id, prospect_id, occurred_at, prospect["created_by"],
                )
                await conn.execute(
                    """UPDATE outreach_followup_enrollments e
                       SET status='stopped_opt_out',next_run_at=NULL,paused_next_run_at=NULL,
                           pause_reason=NULL,last_error_code='email_unsubscribe',updated_at=now()
                       FROM outreach_followup_sequences s
                       WHERE s.id=e.sequence_id AND s.workspace_id=e.workspace_id
                         AND e.workspace_id=$1 AND e.prospect_id=$2 AND s.channel='email'
                         AND e.status IN ('active','awaiting_approval','paused')""",
                    workspace_id, prospect_id,
                )
                await conn.execute(
                    """UPDATE outreach_deliveries q SET status='cancelled',
                       error_code='email_unsubscribe',updated_at=now()
                       FROM outreach_drafts d
                       WHERE q.workspace_id=$1 AND q.draft_id=d.id AND d.workspace_id=q.workspace_id
                         AND d.prospect_id=$2 AND q.channel='email' AND q.status='queued'""",
                    workspace_id, prospect_id,
                )
        return {"unsubscribed": True, "workspace_id": workspace_id, "prospect_id": str(prospect_id)}

    async def list_events(
        self, *, workspace_id: str, delivery_id: UUID, limit: int = 50,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("pagination_out_of_range")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT e.id,e.provider,e.provider_event_id,e.event_type,e.occurred_at,e.received_at
                   FROM email_provider_events e
                   JOIN outreach_deliveries q ON q.id=e.delivery_id
                   WHERE q.id=$1 AND q.workspace_id=$2
                   ORDER BY e.occurred_at DESC,e.id DESC LIMIT $3""",
                delivery_id, workspace_id, limit,
            )
        result = []
        for row in rows:
            item = dict(row)
            item["id"] = str(item["id"])
            result.append(item)
        return result
