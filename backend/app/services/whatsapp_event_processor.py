"""Idempotent worker for the durable Meta WhatsApp webhook inbox.

Invoke from a trusted worker/scheduler with the application DB pool. This module does not
send messages; it only stores inbound conversations and provider delivery-status events.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from uuid import UUID


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
        return parsed
    except (ValueError, OverflowError, OSError):
        return None


def _effective_inbound_timestamp(provider_timestamp: datetime | None, received_at: datetime) -> datetime:
    """Use provider time when valid, but never let it exceed trusted receipt time."""
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("timezone_required")
    if provider_timestamp is None:
        return received_at
    if provider_timestamp.tzinfo is None or provider_timestamp.utcoffset() is None:
        raise ValueError("timezone_required")
    return min(provider_timestamp, received_at)


def _is_opt_out(body: str | None) -> bool:
    """Recognize a standalone opt-out command without matching ordinary prose."""
    if not body:
        return False
    normalized = re.sub(r"[.!?,;:]+$", "", body.strip()).strip().upper()
    return normalized in {"STOP", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}


def _is_opt_in(body: str | None) -> bool:
    """Recognize an explicit standalone START command for renewed consent."""
    if not body:
        return False
    normalized = re.sub(r"[.!?,;:]+$", "", body.strip()).strip().upper()
    return normalized in {"START", "UNSTOP", "SUBSCRIBE"}


def _text(message: dict[str, Any]) -> tuple[str, str | None]:
    kind = message.get("type")
    if not isinstance(kind, str) or not kind:
        kind = "unknown"
    body: str | None = None
    if kind == "text":
        obj = message.get("text")
        if isinstance(obj, dict) and isinstance(obj.get("body"), str):
            body = obj["body"][:10000]
    return kind[:40], body


async def process_pending_whatsapp_events(pool: Any, *, batch_size: int = 25) -> dict[str, int]:
    """Process a bounded batch using row locks; safe for concurrent worker instances."""
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size_out_of_range")
    processed = messages_saved = statuses_saved = unmapped = failed = 0
    for _ in range(batch_size):
        last_event_id = None
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    event = await conn.fetchrow(
                        """SELECT id, phone_number_id, payload, received_at
                           FROM meta_whatsapp_webhook_events
                           WHERE processed_at IS NULL AND attempts < 8
                           ORDER BY received_at, id
                           LIMIT 1 FOR UPDATE SKIP LOCKED"""
                    )
                    if event is None:
                        break
                    last_event_id = event["id"]
                    await conn.execute(
                        "UPDATE meta_whatsapp_webhook_events SET attempts=attempts+1, processing_started_at=now() WHERE id=$1",
                        event["id"],
                    )
                    account = None
                    if event["phone_number_id"]:
                        account = await conn.fetchrow(
                            """SELECT id, workspace_id FROM workspace_whatsapp_accounts
                               WHERE phone_number_id=$1 AND status='active'""",
                            event["phone_number_id"],
                        )
                    payload = event["payload"]
                    if isinstance(payload, str):
                        import json
                        payload = json.loads(payload)
                    if account is None:
                        await conn.execute(
                            """UPDATE meta_whatsapp_webhook_events
                               SET processed_at=now(), processing_error_code='unmapped_or_inactive_phone'
                               WHERE id=$1""",
                            event["id"],
                        )
                        processed += 1
                        unmapped += 1
                        continue

                    workspace_id = str(account["workspace_id"])
                    account_id = account["id"]
                    # Never extend the 24-hour customer-service window with a future
                    # provider timestamp. Fall back to trusted server receipt time.
                    event_received_at = event["received_at"]
                    saved_this_event = 0
                    status_this_event = 0
                    entries = payload.get("entry", []) if isinstance(payload, dict) else []
                    for entry in entries if isinstance(entries, list) else []:
                        if not isinstance(entry, dict):
                            continue
                        changes = entry.get("changes", [])
                        for change in changes if isinstance(changes, list) else []:
                            if not isinstance(change, dict):
                                continue
                            value = change.get("value")
                            if not isinstance(value, dict):
                                continue
                            metadata = value.get("metadata")
                            if not isinstance(metadata, dict) or metadata.get("phone_number_id") != event["phone_number_id"]:
                                continue
                            messages = value.get("messages", [])
                            for msg in messages if isinstance(messages, list) else []:
                                if not isinstance(msg, dict):
                                    continue
                                provider_id = msg.get("id")
                                wa_id = msg.get("from")
                                if not isinstance(provider_id, str) or not provider_id or not isinstance(wa_id, str) or not wa_id.isdigit() or len(wa_id) > 64:
                                    continue
                                prospect = await conn.fetchrow(
                                    """SELECT id FROM crm_prospects
                                       WHERE workspace_id=$1 AND archived_at IS NULL
                                         AND regexp_replace(contact_phone_e164, '[^0-9]', '', 'g')=$2
                                       ORDER BY updated_at DESC LIMIT 1""",
                                    workspace_id, wa_id,
                                )
                                conversation = await conn.fetchrow(
                                    """INSERT INTO whatsapp_conversations(workspace_id,account_id,prospect_id,wa_id)
                                       VALUES($1,$2,$3,$4)
                                       ON CONFLICT(workspace_id,account_id,wa_id) DO UPDATE
                                         SET prospect_id=COALESCE(whatsapp_conversations.prospect_id,EXCLUDED.prospect_id),
                                             updated_at=now()
                                       RETURNING id""",
                                    workspace_id, account_id, prospect["id"] if prospect else None, wa_id,
                                )
                                message_type, body = _text(msg)
                                provider_timestamp = _timestamp(msg.get("timestamp"))
                                inbound_at = _effective_inbound_timestamp(provider_timestamp, event_received_at)
                                inserted = await conn.fetchval(
                                    """INSERT INTO whatsapp_inbound_messages
                                       (workspace_id,conversation_id,provider_message_id,message_type,text_body,provider_timestamp)
                                       VALUES($1,$2,$3,$4,$5,$6)
                                       ON CONFLICT(provider_message_id) DO NOTHING
                                       RETURNING id""",
                                    workspace_id, conversation["id"], provider_id, message_type, body, provider_timestamp,
                                )
                                if inserted:
                                    saved_this_event += 1
                                    await conn.execute(
                                        """INSERT INTO whatsapp_contact_preferences
                                           (workspace_id,account_id,wa_id,last_inbound_at,last_inbound_message_id,updated_at)
                                           VALUES($1,$2,$3,$5,$4,now())
                                           ON CONFLICT(workspace_id,account_id,wa_id) DO UPDATE
                                             SET last_inbound_message_id=CASE
                                                   WHEN whatsapp_contact_preferences.last_inbound_at IS NULL
                                                     OR EXCLUDED.last_inbound_at >= whatsapp_contact_preferences.last_inbound_at
                                                   THEN EXCLUDED.last_inbound_message_id
                                                   ELSE whatsapp_contact_preferences.last_inbound_message_id END,
                                                 last_inbound_at=GREATEST(
                                                   COALESCE(whatsapp_contact_preferences.last_inbound_at, EXCLUDED.last_inbound_at),
                                                   EXCLUDED.last_inbound_at),
                                                 updated_at=now()""",
                                        workspace_id, account_id, wa_id, provider_id, inbound_at,
                                    )
                                    opt_out = _is_opt_out(body)
                                    opt_in = _is_opt_in(body)
                                    if opt_out:
                                        await conn.execute(
                                            """UPDATE whatsapp_contact_preferences
                                               SET opted_out_at=$5, opted_in_at=NULL,
                                                   last_opt_out_message_id=$4, updated_at=now()
                                               WHERE workspace_id=$1 AND account_id=$2 AND wa_id=$3
                                                 AND (opted_out_at IS NULL OR opted_out_at <= $5)
                                                 AND (opted_in_at IS NULL OR opted_in_at <= $5)""",
                                            workspace_id, account_id, wa_id, provider_id, inbound_at,
                                        )
                                        # Cancel queued (not yet dispatched) drafts for this contact.
                                        # The future dispatcher must still re-check policy immediately before send.
                                        if prospect:
                                            await conn.execute(
                                                """WITH cancelled AS (
                                                       UPDATE whatsapp_outbound_deliveries
                                                       SET status='cancelled', error_code='contact_opted_out',
                                                           updated_at=now()
                                                       WHERE workspace_id=$1 AND account_id=$2 AND prospect_id=$3
                                                         AND status='queued'
                                                       RETURNING usage_reservation_id
                                                   )
                                                   UPDATE feature_usage_reservations AS u
                                                   SET status='released', updated_at=now()
                                                   FROM cancelled AS q
                                                   WHERE u.id=q.usage_reservation_id
                                                     AND u.workspace_id=$1 AND u.status='reserved'""",
                                                workspace_id, account_id, prospect["id"],
                                            )
                                    elif opt_in:
                                        # Explicit inbound START-family commands re-enable contact only after
                                        # the contact themselves initiates it; preserve the audit timestamp.
                                        await conn.execute(
                                            """UPDATE whatsapp_contact_preferences
                                               SET opted_in_at=$4, updated_at=now()
                                               WHERE workspace_id=$1 AND account_id=$2 AND wa_id=$3
                                                 AND (opted_out_at IS NULL OR opted_out_at <= $4)
                                                 AND (opted_in_at IS NULL OR opted_in_at <= $4)""",
                                            workspace_id, account_id, wa_id, inbound_at,
                                        )
                                    elif prospect:
                                        await conn.execute(
                                            """UPDATE crm_prospects SET stage='replied', updated_at=now()
                                               WHERE id=$1 AND workspace_id=$2
                                                 AND stage NOT IN ('converted','disqualified','do_not_contact')""",
                                            prospect["id"], workspace_id,
                                        )
                            statuses = value.get("statuses", [])
                            for status in statuses if isinstance(statuses, list) else []:
                                if not isinstance(status, dict):
                                    continue
                                provider_id, state = status.get("id"), status.get("status")
                                recipient = status.get("recipient_id")
                                if not isinstance(provider_id, str) or not provider_id or not isinstance(state, str) or not state:
                                    continue
                                inserted_status = await conn.fetchval(
                                    """INSERT INTO whatsapp_delivery_status_events
                                       (workspace_id,account_id,provider_message_id,recipient_wa_id,status,provider_timestamp,errors)
                                       VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)
                                       ON CONFLICT DO NOTHING RETURNING id""",
                                    workspace_id, account_id, provider_id,
                                    recipient[:64] if isinstance(recipient, str) else None,
                                    state[:40], _timestamp(status.get("timestamp")),
                                    __import__("json").dumps(status.get("errors", []) if isinstance(status.get("errors", []), list) else []),
                                )
                                if inserted_status:
                                    status_this_event += 1
                                # Reconcile only when a future approved dispatcher has
                                # persisted the provider message ID. Status webhooks never
                                # trigger a send and must not move delivery state backwards.
                                target_status = {
                                    "sent": "sent",
                                    "delivered": "delivered",
                                    "read": "read",
                                    "failed": "failed",
                                }.get(state.lower())
                                if target_status:
                                    await conn.execute(
                                        """UPDATE whatsapp_outbound_deliveries
                                           SET status=$3,
                                               sent_at=CASE
                                                 WHEN $3 IN ('sent','delivered','read')
                                                 THEN COALESCE(sent_at, $4)
                                                 ELSE sent_at END,
                                               error_code=CASE
                                                 WHEN $3='failed' THEN 'provider_delivery_failed'
                                                 WHEN $3 IN ('sent','delivered','read') THEN NULL
                                                 ELSE error_code END,
                                               updated_at=now()
                                           WHERE workspace_id=$1 AND account_id=$2
                                             AND provider_message_id=$5
                                             AND status IN ('processing','uncertain','sent','delivered','read')
                                             AND CASE status
                                               WHEN 'processing' THEN 0
                                               WHEN 'uncertain' THEN 0
                                               WHEN 'sent' THEN 1
                                               WHEN 'delivered' THEN 2
                                               WHEN 'read' THEN 3
                                               WHEN 'failed' THEN 4
                                               ELSE 5 END
                                             <= CASE $3
                                               WHEN 'sent' THEN 1
                                               WHEN 'delivered' THEN 2
                                               WHEN 'read' THEN 3
                                               WHEN 'failed' THEN 4
                                               ELSE 5 END""",
                                        workspace_id, account_id, target_status,
                                        _timestamp(status.get("timestamp")), provider_id,
                                    )
                    await conn.execute(
                        """UPDATE meta_whatsapp_webhook_events
                           SET processed_at=now(), processing_error_code=NULL WHERE id=$1""",
                        event["id"],
                    )
                    processed += 1
                    messages_saved += saved_this_event
                    statuses_saved += status_this_event
        except Exception:
            failed += 1
            # Persist a bounded retry counter separately after the failed transaction rolls back.
            # Do not log payloads, phone numbers, provider IDs, or credentials.
            if last_event_id is not None:
                try:
                    async with pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE meta_whatsapp_webhook_events SET attempts=attempts+1, processing_error_code='worker_processing_failed' WHERE id=$1 AND processed_at IS NULL",
                            last_event_id,
                        )
                except Exception:
                    pass
            continue
    return {"processed": processed, "messages_saved": messages_saved, "statuses_saved": statuses_saved, "unmapped": unmapped, "failed": failed}
