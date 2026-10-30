"""Workspace-authorized read-only WhatsApp inbox APIs.

Outbound replies are intentionally not implemented here: future send paths must enforce
documented opt-in, approved templates, account verification, and workspace entitlements.
"""
from __future__ import annotations

import hmac
import json
from uuid import UUID

from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings

class WhatsAppConversationUpdate(BaseModel):
    assigned_to_user_id: str | None = Field(default=None, min_length=1, max_length=200)
    inbox_status: str | None = Field(default=None, pattern="^(open|pending|resolved)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high|urgent)$")


class WhatsAppInternalNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


router = APIRouter(prefix="/api/v1/integrations/whatsapp/inbox", tags=["WhatsApp inbox"])


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="whatsapp_inbox_not_configured")
    return pool


async def _authorize(request: Request, workspace_id: str, session: dict, role: str = "viewer") -> None:
    auth = getattr(request.app.state, "auth_store", None)
    if auth is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")


def _serialize(row: dict) -> dict:
    for key, value in list(row.items()):
        if isinstance(value, UUID):
            row[key] = str(value)
        elif hasattr(value, "isoformat"):
            row[key] = value.isoformat()
    return row


@router.get("/conversations")
async def list_whatsapp_conversations(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    assigned_to_me: bool = Query(default=False),
    unassigned: bool = Query(default=False),
    inbox_status: str | None = Query(default=None, pattern="^(open|pending|resolved)$"),
    priority: str | None = Query(default=None, pattern="^(low|normal|high|urgent)$"),
    search: str | None = Query(default=None, min_length=1, max_length=200),
) -> dict:
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, session)
    try:
        user_id = str(session["user_id"])
        search_term = search.strip() if search else None
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.id, c.workspace_id, c.account_id, c.prospect_id, c.wa_id,
                          c.assigned_to_user_id,c.inbox_status,c.priority,c.assigned_at,c.closed_at,
                          c.created_at, c.updated_at, a.label AS account_label,
                          p.name AS prospect_name, p.company AS prospect_company,
                          m.text_body AS last_message_text, m.message_type AS last_message_type,
                          m.received_at AS last_message_at
                   FROM whatsapp_conversations c
                   JOIN workspace_whatsapp_accounts a
                     ON a.id=c.account_id AND a.workspace_id=c.workspace_id
                   LEFT JOIN crm_prospects p
                     ON p.id=c.prospect_id AND p.workspace_id=c.workspace_id
                   LEFT JOIN LATERAL (
                       SELECT text_body, message_type, received_at
                       FROM whatsapp_inbound_messages
                       WHERE conversation_id=c.id AND workspace_id=c.workspace_id
                       ORDER BY received_at DESC, id DESC LIMIT 1
                   ) m ON TRUE
                   WHERE c.workspace_id=$1
                     AND (NOT $4::boolean OR c.assigned_to_user_id=$5)
                     AND (NOT $6::boolean OR c.assigned_to_user_id IS NULL)
                     AND ($7::text IS NULL OR c.inbox_status=$7)
                     AND ($8::text IS NULL OR c.priority=$8)
                     AND ($9::text IS NULL OR
                          c.wa_id ILIKE '%' || $9 || '%' OR
                          COALESCE(p.name,'') ILIKE '%' || $9 || '%' OR
                          COALESCE(p.company,'') ILIKE '%' || $9 || '%' OR
                          COALESCE(m.text_body,'') ILIKE '%' || $9 || '%')
                   ORDER BY COALESCE(m.received_at,c.updated_at) DESC,c.id
                   LIMIT $2 OFFSET $3""",
                workspace_id, limit, offset, assigned_to_me, user_id,
                unassigned, inbox_status, priority, search_term,
            )
        return {"items": [_serialize(dict(row)) for row in rows], "limit": limit, "offset": offset}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_conversation_list_unavailable") from None


@router.get("/conversations/{conversation_id}/messages")
async def list_whatsapp_messages(
    conversation_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    before: str | None = Query(default=None, max_length=64),
) -> dict:
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, session)
    try:
        async with _pool(request).acquire() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM whatsapp_conversations WHERE id=$1 AND workspace_id=$2)",
                conversation_id, workspace_id,
            )
            if not exists:
                raise HTTPException(status_code=404, detail="whatsapp_conversation_not_found")
            if before:
                try:
                    before_id = UUID(before)
                except ValueError:
                    raise HTTPException(status_code=422, detail="invalid_before_message_id") from None
                rows = await conn.fetch(
                    """SELECT id, conversation_id, provider_message_id, message_type, text_body,
                              media_metadata, media_mime_type, media_filename, media_size, media_downloaded_at,
                              provider_timestamp, received_at
                       FROM whatsapp_inbound_messages
                       WHERE workspace_id=$1 AND conversation_id=$2
                         AND (received_at, id) < (
                           SELECT received_at, id FROM whatsapp_inbound_messages
                           WHERE id=$3 AND workspace_id=$1 AND conversation_id=$2
                         )
                       ORDER BY received_at DESC,id DESC LIMIT $4""",
                    workspace_id, conversation_id, before_id, limit,
                )
            else:
                rows = await conn.fetch(
                    """SELECT id, conversation_id, provider_message_id, message_type, text_body,
                              media_metadata, media_mime_type, media_filename, media_size, media_downloaded_at,
                              provider_timestamp, received_at
                       FROM whatsapp_inbound_messages
                       WHERE workspace_id=$1 AND conversation_id=$2
                       ORDER BY received_at DESC,id DESC LIMIT $3""",
                    workspace_id, conversation_id, limit,
                )
        items = [_serialize(dict(row)) for row in rows]
        for item in items:
            if isinstance(item.get("media_metadata"), str):
                item["media_metadata"] = json.loads(item["media_metadata"])
        return {"items": items, "limit": limit, "has_more": len(items) == limit}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_message_list_unavailable") from None

@router.get("/webhook-events")
async def list_whatsapp_webhook_events(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    state: str = Query(default="pending", pattern="^(pending|processed|dead_letter|all)$"),
) -> dict:
    """Expose safe processing metadata for this workspace's mapped Meta accounts only.

    Raw provider payloads, message text, signatures, and access tokens are never returned.
    This is an operational inbox view, not a processing/retry trigger.
    """
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, session)
    try:
        async with _pool(request).acquire() as conn:
            # Account IDs are globally unique; the workspace join is the tenant boundary.
            rows = await conn.fetch(
                """SELECT e.id, e.phone_number_id, e.event_kind, e.received_at,
                          e.processed_at, e.processing_error_code
                   FROM meta_whatsapp_webhook_events e
                   JOIN workspace_whatsapp_accounts a
                     ON a.phone_number_id=e.phone_number_id
                    AND a.workspace_id=$1
                   WHERE ($2='all'
                     OR ($2='pending' AND e.processed_at IS NULL AND e.attempts < 8)
                     OR ($2='dead_letter' AND e.processed_at IS NULL AND e.attempts >= 8)
                     OR ($2='processed' AND e.processed_at IS NOT NULL))
                   ORDER BY e.received_at DESC,e.id DESC
                   LIMIT $3 OFFSET $4""",
                workspace_id, state, limit, offset,
            )
            counts = await conn.fetchrow(
                """SELECT count(*) FILTER (WHERE e.processed_at IS NULL AND e.attempts < 8)::bigint AS pending,
                          count(*) FILTER (WHERE e.processed_at IS NULL AND e.attempts >= 8)::bigint AS dead_letter,
                          count(*) FILTER (WHERE e.processed_at IS NOT NULL)::bigint AS processed,
                          count(*) FILTER (WHERE e.processing_error_code IS NOT NULL)::bigint AS with_errors
                   FROM meta_whatsapp_webhook_events e
                   JOIN workspace_whatsapp_accounts a
                     ON a.phone_number_id=e.phone_number_id
                    AND a.workspace_id=$1""",
                workspace_id,
            )
        items = []
        for row in rows:
            item = dict(row)
            item["id"] = str(item["id"])
            for key in ("received_at", "processed_at"):
                if item.get(key) is not None:
                    item[key] = item[key].isoformat()
            items.append(item)
        return {
            "items": items,
            "counts": {key: int(value or 0) for key, value in dict(counts).items()},
            "state": state,
            "limit": limit,
            "offset": offset,
            "notice": "Only processing metadata for mapped workspace accounts is shown; event payloads are withheld.",
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_webhook_event_list_unavailable") from None

@router.post("/webhook-events/{event_id}/retry")
async def retry_dead_letter_whatsapp_event(
    event_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    """Explicitly requeue one exhausted event after workspace-admin review.

    This does not send messages. Provider message IDs remain deduplicated by the worker.
    """
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, session, role="admin")
    try:
        async with _pool(request).acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """UPDATE meta_whatsapp_webhook_events e
                       SET attempts=0, processing_error_code=NULL, processing_started_at=NULL
                       WHERE e.id=$1 AND e.processed_at IS NULL AND e.attempts >= 8
                         AND EXISTS (
                           SELECT 1 FROM workspace_whatsapp_accounts a
                           WHERE a.workspace_id=$2 AND a.phone_number_id=e.phone_number_id
                             AND a.status='active'
                         )
                       RETURNING e.id""",
                    event_id, workspace_id,
                )
        if row is None:
            raise HTTPException(status_code=404, detail="retryable_workspace_dead_letter_not_found")
        return {
            "event_id": str(row["id"]),
            "state": "pending",
            "notice": "One exhausted event was requeued. Processing occurs only when the trusted worker next runs.",
            "outbound_sending_enabled": False,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_event_retry_unavailable") from None


@router.post("/webhook-events/process-pending")
async def process_pending_whatsapp_events_for_workspace(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    batch_size: int = Query(default=25, ge=1, le=100),
) -> dict:
    """Admin-triggered, bounded processing limited to this workspace's active accounts."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, session, role="admin")
    try:
        from app.services.whatsapp_event_processor import process_pending_whatsapp_events

        result = await process_pending_whatsapp_events(
            _pool(request), batch_size=batch_size, workspace_id=workspace_id,
        )
        return {
            "workspace_id": workspace_id,
            **result,
            "outbound_sending_enabled": False,
            "notice": "Inbound events processed only for this workspace's active WhatsApp accounts. No messages were sent.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_event_processing_unavailable") from None



@router.post("/webhook-events/process-pending-system")
async def process_pending_whatsapp_events_system(
    request: Request, batch_size: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Scheduler-only global inbound event processor for all active mapped accounts."""
    configured = (settings.cron_secret or "").strip()
    if len(configured.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="whatsapp_worker_secret_not_configured")
    supplied = request.headers.get("authorization", "")
    scheme, _, token = supplied.partition(" ")
    if scheme.lower() != "bearer" or not token or not hmac.compare_digest(configured, token):
        raise HTTPException(status_code=401, detail="invalid_scheduler_authorization")
    try:
        pool = _pool(request)
        from app.services.whatsapp_event_processor import process_pending_whatsapp_events
        from app.services.whatsapp_status_reconciliation import reconcile_whatsapp_delivery_statuses
        result = await process_pending_whatsapp_events(pool, batch_size=batch_size)
        reconciliation = await reconcile_whatsapp_delivery_statuses(pool, batch_size=500)
        return {"accepted": True, **result, "status_reconciliation": reconciliation}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_inbound_processing_unavailable") from None


@router.post("/messages/{message_id}/media/download")
async def download_whatsapp_inbound_media(
    message_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    account_id: UUID = Query(),
) -> dict:
    """Fetch a Meta attachment once and store it encrypted with workspace/account AAD."""
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, session, "admin")
    from app.services.whatsapp_media_store import WhatsAppMediaError, download_meta_media
    try:
        return await download_meta_media(
            pool=_pool(request), workspace_id=workspace_id,
            account_id=account_id, message_id=message_id,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="whatsapp_media_message_not_found") from None
    except WhatsAppMediaError as exc:
        code = str(exc)
        status = 413 if code == "whatsapp_media_too_large" else 422
        raise HTTPException(status_code=status, detail=code) from None
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_media_download_unavailable") from None


@router.get("/messages/{message_id}/media")
async def get_whatsapp_inbound_media(
    message_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> Response:
    """Return decrypted media only after verifying the conversation's workspace access."""
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, session, "viewer")
    from app.services.whatsapp_media_store import WhatsAppMediaError, decrypt_media
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """SELECT m.media_ciphertext,m.media_mime_type,m.media_filename,
                          m.media_size,c.account_id
                   FROM whatsapp_inbound_messages m
                   JOIN whatsapp_conversations c ON c.id=m.conversation_id
                     AND c.workspace_id=m.workspace_id
                   WHERE m.id=$1 AND m.workspace_id=$2""",
                message_id, workspace_id,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="whatsapp_media_message_not_found")
        if row["media_ciphertext"] is None:
            raise HTTPException(status_code=404, detail="whatsapp_media_not_downloaded")
        content = decrypt_media(
            row["media_ciphertext"], workspace_id, row["account_id"], message_id,
        )
        mime = str(row["media_mime_type"] or "application/octet-stream")
        filename = str(row["media_filename"] or "whatsapp-attachment")
        filename = "".join(ch for ch in filename if ch.isascii() and (ch.isalnum() or ch in "._-"))[:180]
        return Response(
            content=content,
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(content)),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )
    except HTTPException:
        raise
    except WhatsAppMediaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_media_retrieval_unavailable") from None


@router.delete("/messages/{message_id}/media")
async def delete_whatsapp_inbound_media(
    message_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    """Permanently remove an encrypted attachment while retaining the message record."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, session, "admin")
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE whatsapp_inbound_messages m
                   SET media_ciphertext=NULL,media_mime_type=NULL,media_filename=NULL,
                       media_size=NULL,media_downloaded_at=NULL
                   FROM whatsapp_conversations c
                   WHERE m.id=$1 AND m.workspace_id=$2
                     AND c.id=m.conversation_id AND c.workspace_id=m.workspace_id
                     AND m.media_ciphertext IS NOT NULL
                   RETURNING m.id""",
                message_id, workspace_id,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="stored_whatsapp_media_not_found")
        return {"message_id": str(row["id"]), "deleted": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_media_delete_unavailable") from None


@router.patch("/conversations/{conversation_id}")
async def update_whatsapp_conversation(
    conversation_id: UUID,
    payload: WhatsAppConversationUpdate,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    """Assign, prioritize and change lifecycle state with an immutable activity trail."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, session, role="admin")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="whatsapp_conversation_update_empty")
    assignee = changes.get("assigned_to_user_id")
    try:
        if "assigned_to_user_id" in changes and assignee is not None:
            auth = getattr(request.app.state, "auth_store", None)
            if auth is None or not await auth.authorize_workspace(
                user_id=assignee, workspace_id=workspace_id, minimum_role="viewer"
            ):
                raise HTTPException(status_code=422, detail="whatsapp_assignee_not_workspace_member")
        assignments, args = [], [conversation_id, workspace_id]
        if "assigned_to_user_id" in changes:
            args.append(assignee)
            assignments.append(f"assigned_to_user_id=${len(args)}")
            assignments.append("assigned_at=CASE WHEN $" + str(len(args)) + " IS NULL THEN NULL ELSE now() END")
        if "inbox_status" in changes:
            args.append(changes["inbox_status"])
            assignments.append(f"inbox_status=${len(args)}")
            assignments.append("closed_at=CASE WHEN $" + str(len(args)) + "='resolved' THEN now() ELSE NULL END")
        if "priority" in changes:
            args.append(changes["priority"])
            assignments.append(f"priority=${len(args)}")
        assignments.append("updated_at=now()")
        async with _pool(request).acquire() as conn:
            async with conn.transaction():
                old = await conn.fetchrow(
                    """SELECT assigned_to_user_id,inbox_status,priority
                       FROM whatsapp_conversations WHERE id=$1 AND workspace_id=$2 FOR UPDATE""",
                    conversation_id, workspace_id,
                )
                if old is None:
                    raise HTTPException(status_code=404, detail="whatsapp_conversation_not_found")
                row = await conn.fetchrow(
                    "UPDATE whatsapp_conversations SET " + ",".join(assignments) +
                    " WHERE id=$1 AND workspace_id=$2 RETURNING id,assigned_to_user_id,inbox_status,priority,assigned_at,closed_at,updated_at",
                    *args,
                )
                event_map = {
                    "assigned_to_user_id": "assignment_changed",
                    "inbox_status": "status_changed",
                    "priority": "priority_changed",
                }
                for field, event_type in event_map.items():
                    if field in changes and str(old[field] or "") != str(changes[field] or ""):
                        await conn.execute(
                            """INSERT INTO whatsapp_conversation_activity
                               (workspace_id,conversation_id,actor_user_id,event_type,details)
                               VALUES ($1,$2,$3,$4,$5::jsonb)""",
                            workspace_id, conversation_id, str(session["user_id"]), event_type,
                            json.dumps({"from": old[field], "to": changes[field]}),
                        )
        return _serialize(dict(row))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_conversation_update_unavailable") from None


@router.get("/conversations/{conversation_id}/activity")
async def list_whatsapp_conversation_activity(
    conversation_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    before_id: UUID | None = Query(default=None),
) -> dict:
    """Return workspace-scoped, append-only conversation activity metadata."""
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, session, role="viewer")
    try:
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT a.id,a.actor_user_id,a.event_type,a.details,a.created_at
                   FROM whatsapp_conversation_activity a
                   JOIN whatsapp_conversations c ON c.id=a.conversation_id
                     AND c.workspace_id=a.workspace_id
                   WHERE a.workspace_id=$1 AND a.conversation_id=$2
                     AND ($4::uuid IS NULL OR (a.created_at,a.id) < (
                       SELECT created_at,id FROM whatsapp_conversation_activity
                       WHERE id=$4 AND workspace_id=$1 AND conversation_id=$2
                     ))
                   ORDER BY a.created_at DESC,a.id DESC LIMIT $3""",
                workspace_id, conversation_id, limit, before_id,
            )
        items = []
        for row in rows:
            item = _serialize(dict(row))
            if isinstance(item.get("details"), str):
                item["details"] = json.loads(item["details"])
            items.append(item)
        return {"items": items, "limit": limit, "has_more": len(items) == limit}
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_conversation_activity_unavailable") from None


@router.get("/conversations/{conversation_id}/notes")
async def list_whatsapp_conversation_notes(
    conversation_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, session, "viewer")
    try:
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT n.id,n.conversation_id,n.author_user_id,n.body,n.created_at,n.updated_at
                   FROM whatsapp_conversation_notes n
                   JOIN whatsapp_conversations c ON c.id=n.conversation_id
                     AND c.workspace_id=n.workspace_id
                   WHERE n.workspace_id=$1 AND n.conversation_id=$2
                   ORDER BY n.created_at DESC,n.id DESC LIMIT $3""",
                workspace_id, conversation_id, limit,
            )
        return {"items": [_serialize(dict(row)) for row in rows], "limit": limit}
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_conversation_notes_unavailable") from None


@router.post("/conversations/{conversation_id}/notes")
async def create_whatsapp_conversation_note(
    conversation_id: UUID,
    payload: WhatsAppInternalNoteCreate,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    """Create an internal-only note; note text is never sent to Meta or the contact."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, session, "member")
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="whatsapp_internal_note_empty")
    try:
        async with _pool(request).acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """INSERT INTO whatsapp_conversation_notes
                       (workspace_id,conversation_id,author_user_id,body)
                       SELECT $1,c.id,$3,$4 FROM whatsapp_conversations c
                       WHERE c.id=$2 AND c.workspace_id=$1
                       RETURNING id,conversation_id,author_user_id,body,created_at,updated_at""",
                    workspace_id, conversation_id, session["user_id"], body,
                )
                if row is not None:
                    await conn.execute(
                        """INSERT INTO whatsapp_conversation_activity
                           (workspace_id,conversation_id,actor_user_id,event_type,details)
                           VALUES ($1,$2,$3,'note_added',$4::jsonb)""",
                        workspace_id, conversation_id, str(session["user_id"]),
                        json.dumps({"note_id": str(row["id"])}),
                    )
        if row is None:
            raise HTTPException(status_code=404, detail="whatsapp_conversation_not_found")
        return _serialize(dict(row))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_internal_note_create_unavailable") from None


@router.delete("/conversations/{conversation_id}/notes/{note_id}")
async def delete_whatsapp_conversation_note(
    conversation_id: UUID,
    note_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, session, "admin")
    try:
        async with _pool(request).acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """DELETE FROM whatsapp_conversation_notes n
                       USING whatsapp_conversations c
                       WHERE n.id=$1 AND n.conversation_id=$2 AND n.workspace_id=$3
                         AND c.id=n.conversation_id AND c.workspace_id=n.workspace_id
                       RETURNING n.id""",
                    note_id, conversation_id, workspace_id,
                )
                if row is not None:
                    await conn.execute(
                        """INSERT INTO whatsapp_conversation_activity
                           (workspace_id,conversation_id,actor_user_id,event_type,details)
                           VALUES ($1,$2,$3,'note_deleted',$4::jsonb)""",
                        workspace_id, conversation_id, str(session["user_id"]),
                        json.dumps({"note_id": str(row["id"])}),
                    )
        if row is None:
            raise HTTPException(status_code=404, detail="whatsapp_internal_note_not_found")
        return {"note_id": str(row["id"]), "deleted": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_internal_note_delete_unavailable") from None
