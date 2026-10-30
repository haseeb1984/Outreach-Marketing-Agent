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
                    """SELECT q.id,q.workspace_id,q.provider_status,q.provider_status_at,
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
