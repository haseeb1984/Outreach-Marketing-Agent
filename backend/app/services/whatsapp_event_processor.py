"""Idempotent worker for the durable Meta WhatsApp webhook inbox.

Invoke from a trusted worker/scheduler with the application DB pool. This module does not
send messages; it only stores inbound conversations and provider delivery-status events.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
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


def _delivery_status_target(value: Any) -> str | None:
    """Normalize only documented Meta delivery states into internal queue states."""
    if not isinstance(value, str):
        return None
    return {
        "sent": "sent",
        "delivered": "delivered",
        "read": "read",
        "failed": "failed",
    }.get(value.strip().lower())


def _media_metadata(message: dict[str, Any], kind: str) -> dict[str, Any]:
    """Persist safe media and interactive metadata without fetching provider media."""
    value = message.get(kind)
    if kind in {"image", "video", "audio", "document", "sticker"} and isinstance(value, dict):
        allowed = ("id", "mime_type", "sha256", "caption", "filename", "voice", "animated")
        return {key: value[key] for key in allowed if isinstance(value.get(key), (str, bool)) and len(str(value[key])) <= 2048}
    if kind == "location" and isinstance(value, dict):
        allowed = ("latitude", "longitude", "name", "address")
        return {key: value[key] for key in allowed if isinstance(value.get(key), (str, int, float)) and len(str(value[key])) <= 512}
    if kind == "interactive" and isinstance(value, dict):
        result: dict[str, Any] = {"type": str(value.get("type") or "")[:40]}
        for key in ("button_reply", "list_reply"):
            item = value.get(key)
            if isinstance(item, dict):
                result[key] = {name: item[name] for name in ("id", "title", "description") if isinstance(item.get(name), str) and len(item[name]) <= 512}
        return result
    return {}


def _unique_prospect_id(matches: Any) -> Any | None:
    """Only associate a phone with a prospect when the workspace match is unique."""
    if not isinstance(matches, (list, tuple)) or len(matches) != 1:
        return None
    try:
        return matches[0]["id"]
    except (KeyError, TypeError, IndexError):
        return None


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


async def process_pending_whatsapp_events(
    pool: Any, *, batch_size: int = 25, workspace_id: str | None = None,
) -> dict[str, int]:
    """Process a bounded batch, optionally scoped to one workspace's active accounts.

    Workspace-triggered runs must not claim another tenant's webhook events.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 100:
        raise ValueError("batch_size_out_of_range")
    if workspace_id is not None and (
        not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200
    ):
        raise ValueError("workspace_id_invalid")
    requested_workspace_id = workspace_id
    processed = messages_saved = statuses_saved = unmapped = failed = 0
    for _ in range(batch_size):
        last_event_id = None
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    if requested_workspace_id is None:
                        event = await conn.fetchrow(
                            """SELECT id, phone_number_id, payload, received_at
                               FROM meta_whatsapp_webhook_events
                               WHERE processed_at IS NULL AND attempts < 8
                               ORDER BY received_at, id
                               LIMIT 1 FOR UPDATE SKIP LOCKED"""
                        )
                    else:
                        event = await conn.fetchrow(
                            """SELECT e.id, e.phone_number_id, e.payload, e.received_at
                               FROM meta_whatsapp_webhook_events e
                               WHERE e.processed_at IS NULL AND e.attempts < 8
                                 AND EXISTS (
                                   SELECT 1 FROM workspace_whatsapp_accounts a
                                   WHERE a.phone_number_id=e.phone_number_id
                                     AND a.workspace_id=$1 AND a.status='active'
                                 )
                               ORDER BY e.received_at, e.id
                               LIMIT 1 FOR UPDATE OF e SKIP LOCKED""",
                            requested_workspace_id,
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
                                prospect_matches = await conn.fetch(
                                    """SELECT id FROM crm_prospects
                                       WHERE workspace_id=$1 AND archived_at IS NULL
                                         AND regexp_replace(contact_phone_e164, '[^0-9]', '', 'g')=$2
                                       ORDER BY id LIMIT 2""",
                                    workspace_id, wa_id,
                                )
                                prospect_id = _unique_prospect_id(prospect_matches)
                                conversation = await conn.fetchrow(
                                    """INSERT INTO whatsapp_conversations(workspace_id,account_id,prospect_id,wa_id)
                                       VALUES($1,$2,$3,$4)
                                       ON CONFLICT(workspace_id,account_id,wa_id) DO UPDATE
                                         SET prospect_id=COALESCE(whatsapp_conversations.prospect_id,EXCLUDED.prospect_id),
                                             updated_at=now()
                                       RETURNING id""",
                                    workspace_id, account_id, prospect_id, wa_id,
                                )
                                message_type, body = _text(msg)
                                media_metadata = _media_metadata(msg, message_type)
                                provider_timestamp = _timestamp(msg.get("timestamp"))
                                inbound_at = _effective_inbound_timestamp(provider_timestamp, event_received_at)
                                inserted = await conn.fetchval(
                                    """INSERT INTO whatsapp_inbound_messages
                                       (workspace_id,conversation_id,provider_message_id,message_type,text_body,provider_timestamp,media_metadata)
                                       VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)
                                       ON CONFLICT(provider_message_id) DO NOTHING
                                       RETURNING id""",
                                    workspace_id, conversation["id"], provider_id, message_type, body, provider_timestamp, json.dumps(media_metadata),
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
                                        # Opt-out terminates every WhatsApp follow-up for this contact now.
                                        # Preserve current_draft_id for audit/history; never schedule another step.
                                        if prospect_id:
                                            await conn.execute(
                                                """UPDATE outreach_followup_enrollments e
                                                   SET status='stopped_opt_out',next_run_at=NULL,paused_next_run_at=NULL,
                                                       pause_reason=NULL,last_error_code='whatsapp_contact_opted_out',updated_at=now()
                                                   FROM outreach_followup_sequences s
                                                   WHERE s.id=e.sequence_id AND s.workspace_id=e.workspace_id
                                                     AND e.workspace_id=$1 AND e.prospect_id=$2 AND s.channel='whatsapp'
                                                     AND e.status IN ('active','awaiting_approval','paused')""",
                                                workspace_id, prospect_id,
                                            )
                                            # Cancel queued (not yet dispatched) drafts for this contact.
                                            # The future dispatcher must still re-check policy immediately before send.
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
                                    elif prospect_id:
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
                                target_status = _delivery_status_target(state)
                                if target_status:
                                    updated_delivery = await conn.fetchrow(
                                        """UPDATE whatsapp_outbound_deliveries
                                           SET status=$3,
                                               sent_at=CASE
                                                 WHEN $3 IN ('sent','delivered','read')
                                                 THEN COALESCE(sent_at, $4, now())
                                                 ELSE sent_at END,
                                               error_code=CASE
                                                 WHEN $3='failed' THEN 'provider_delivery_failed'
                                                 WHEN $3 IN ('sent','delivered','read') THEN NULL
                                                 ELSE error_code END,
                                               updated_at=now()
                                           WHERE workspace_id=$1 AND account_id=$2
                                             AND provider_message_id=$5
                                             AND status IN ('processing','uncertain','sent','delivered','read','failed')
                                             AND ($3 <> 'failed' OR status IN ('processing','uncertain','sent','failed'))
                                             AND ($3 <> 'failed' OR NOT EXISTS (
                                               SELECT 1 FROM whatsapp_delivery_status_events newer
                                               WHERE newer.workspace_id=$1 AND newer.account_id=$2
                                                 AND newer.provider_message_id=$5
                                                 AND newer.status IN ('sent','delivered','read')
                                                 AND COALESCE(newer.provider_timestamp,newer.received_at)
                                                     > COALESCE($4,$6)
                                             ))
                                             AND CASE status
                                               WHEN 'processing' THEN 0
                                               WHEN 'uncertain' THEN 0
                                               WHEN 'sent' THEN 1
                                               WHEN 'failed' THEN 0
                                               WHEN 'delivered' THEN 2
                                               WHEN 'read' THEN 3
                                               ELSE 5 END
                                             <= CASE $3
                                               WHEN 'sent' THEN 1
                                               WHEN 'failed' THEN 1
                                               WHEN 'delivered' THEN 2
                                               WHEN 'read' THEN 3
                                               ELSE 5 END
                                           RETURNING id,draft_id""",
                                        workspace_id, account_id, target_status,
                                        _timestamp(status.get("timestamp")), provider_id, event_received_at,
                                    )
                                    if updated_delivery and target_status == "failed":
                                        # A provider-confirmed failure pauses this exact follow-up.
                                        # It must never advance or be blindly retried by the scheduler.
                                        await conn.execute(
                                            """UPDATE outreach_followup_enrollments
                                               SET status='paused',pause_reason='delivery_failed',
                                                   paused_next_run_at=next_run_at,next_run_at=NULL,
                                                   last_error_code='whatsapp_provider_delivery_failed',
                                                   updated_at=now()
                                               WHERE workspace_id=$1 AND current_draft_id=$2
                                                 AND status='awaiting_approval'""",
                                            workspace_id, updated_delivery["draft_id"],
                                        )
                                    elif updated_delivery and target_status in {"delivered", "read"}:
                                        await conn.execute(
                                            """WITH target AS (
                                                   SELECT e.id,e.sequence_id,e.current_step
                                                   FROM outreach_followup_enrollments e
                                                   WHERE e.workspace_id=$1 AND e.current_draft_id=$2
                                                     AND e.status IN ('awaiting_approval','paused')
                                                     AND (e.status='awaiting_approval' OR e.pause_reason IN ('delivery_failed','delivery_uncertain'))
                                                   FOR UPDATE
                                               ), next_step AS (
                                                   SELECT t.id,t.current_step+1 AS step_number,st.delay_minutes
                                                   FROM target t
                                                   LEFT JOIN outreach_followup_steps st
                                                     ON st.sequence_id=t.sequence_id AND st.step_number=t.current_step+1
                                               )
                                               UPDATE outreach_followup_enrollments e
                                               SET status=CASE WHEN n.delay_minutes IS NULL THEN 'completed' ELSE 'active' END,
                                                   current_step=CASE WHEN n.delay_minutes IS NULL THEN e.current_step ELSE n.step_number END,
                                                   current_draft_id=NULL,last_whatsapp_delivery_id=$3,
                                                   next_run_at=CASE WHEN n.delay_minutes IS NULL THEN NULL
                                                                    ELSE now()+(n.delay_minutes * interval '1 minute') END,
                                                   paused_next_run_at=NULL,pause_reason=NULL,last_error_code=NULL,updated_at=now()
                                               FROM next_step n WHERE e.id=n.id""",
                                            workspace_id, updated_delivery["draft_id"], updated_delivery["id"],
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
