"""Reconcile persisted Meta status events against outbound rows after webhook races.

Meta can deliver a status callback before the dispatch worker persists the provider
message ID. The event processor durably records that callback; this bounded reconciler
replays known statuses later and never triggers a send.
"""
from __future__ import annotations

from typing import Any


def _status_target(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return {
        "sent": "sent",
        "delivered": "delivered",
        "read": "read",
        "failed": "failed",
    }.get(value.strip().lower())


async def reconcile_whatsapp_delivery_statuses(
    pool: Any, *, batch_size: int = 250, workspace_id: str | None = None,
) -> dict[str, int]:
    """Replay a bounded set of status events whose outbound row is now identifiable.

    Tenant scope is always enforced by matching workspace and account IDs. Statuses
    progress monotonically; a late 'sent' callback cannot regress delivered/read, and
    a late failed callback cannot overwrite a confirmed delivered/read state.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 2000:
        raise ValueError("batch_size_out_of_range")
    if workspace_id is not None and (
        not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200
    ):
        raise ValueError("workspace_id_invalid")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """WITH candidates AS (
                   SELECT e.workspace_id, e.account_id, e.provider_message_id,
                          e.status, e.provider_timestamp, e.received_at,
                          CASE e.status
                            WHEN 'failed' THEN 1
                            WHEN 'sent' THEN 1
                            WHEN 'delivered' THEN 2
                            WHEN 'read' THEN 3
                            ELSE -1
                          END AS status_rank
                   FROM whatsapp_delivery_status_events e
                   WHERE e.status IN ('sent','delivered','read','failed')
                     AND ($2::text IS NULL OR e.workspace_id=$2)
                     AND EXISTS (
                       SELECT 1 FROM whatsapp_outbound_deliveries d
                       WHERE d.workspace_id=e.workspace_id
                         AND d.account_id=e.account_id
                         AND d.provider_message_id=e.provider_message_id
                         AND (
                           (e.status='sent' AND d.status IN ('processing','uncertain','failed'))
                           OR (e.status='delivered' AND d.status IN ('processing','uncertain','sent','failed'))
                           OR (e.status='read' AND d.status IN ('processing','uncertain','sent','delivered','failed'))
                           OR (e.status='failed' AND d.status IN ('processing','uncertain','sent')
                               AND NOT EXISTS (
                                 SELECT 1 FROM whatsapp_delivery_status_events positive
                                 WHERE positive.workspace_id=e.workspace_id
                                   AND positive.account_id=e.account_id
                                   AND positive.provider_message_id=e.provider_message_id
                                   AND positive.status IN ('delivered','read')
                               ))
                         )
                     )
                   ORDER BY e.received_at DESC, e.id DESC
                   LIMIT $1
               ), latest AS (
                   SELECT DISTINCT ON (workspace_id, account_id, provider_message_id)
                          workspace_id, account_id, provider_message_id, status,
                          provider_timestamp, status_rank
                   FROM candidates
                   ORDER BY workspace_id, account_id, provider_message_id,
                            provider_timestamp DESC NULLS LAST, status_rank DESC
               )
               UPDATE whatsapp_outbound_deliveries d
               SET status=l.status,
                   sent_at=CASE WHEN l.status IN ('sent','delivered','read')
                                THEN COALESCE(d.sent_at,l.provider_timestamp,now())
                                ELSE d.sent_at END,
                   error_code=CASE WHEN l.status='failed'
                                   THEN 'provider_delivery_failed'
                                   WHEN l.status IN ('sent','delivered','read')
                                   THEN NULL ELSE d.error_code END,
                   updated_at=now()
               FROM latest l
               WHERE d.workspace_id=l.workspace_id
                 AND d.account_id=l.account_id
                 AND d.provider_message_id=l.provider_message_id
                 AND (
                   (l.status='sent' AND d.status IN ('processing','uncertain','sent','failed'))
                   OR (l.status='delivered' AND d.status IN ('processing','uncertain','sent','delivered','failed'))
                   OR (l.status='read' AND d.status IN ('processing','uncertain','sent','delivered','read','failed'))
                   OR (l.status='failed' AND d.status IN ('processing','uncertain','sent','failed')
                       AND NOT EXISTS (
                         SELECT 1 FROM whatsapp_delivery_status_events newer
                         WHERE newer.workspace_id=l.workspace_id
                           AND newer.account_id=l.account_id
                           AND newer.provider_message_id=l.provider_message_id
                           AND newer.status IN ('delivered','read')
                       ))
                 )
               RETURNING d.id""",
            batch_size, workspace_id,
        )
    return {"events_considered": len(rows), "deliveries_updated": len(rows)}
