"""Workspace-authorized read-only WhatsApp inbox APIs.

Outbound replies are intentionally not implemented here: future send paths must enforce
documented opt-in, approved templates, account verification, and workspace entitlements.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.auth_routes import _authenticated, _check_csrf

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
) -> dict:
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, session)
    try:
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.id, c.workspace_id, c.account_id, c.prospect_id, c.wa_id,
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
                   ORDER BY COALESCE(m.received_at,c.updated_at) DESC,c.id
                   LIMIT $2 OFFSET $3""",
                workspace_id, limit, offset,
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
                              provider_timestamp, received_at
                       FROM whatsapp_inbound_messages
                       WHERE workspace_id=$1 AND conversation_id=$2
                       ORDER BY received_at DESC,id DESC LIMIT $3""",
                    workspace_id, conversation_id, limit,
                )
        items = [_serialize(dict(row)) for row in rows]
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
\n