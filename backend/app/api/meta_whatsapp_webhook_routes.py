"""Native Meta WhatsApp webhook verification and durable, deduplicated event inbox.

This endpoint does not send WhatsApp messages or expose inbound payloads. Provider events
are stored for a later tenant-mapping/consent-aware processing worker.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.core.config import settings

router = APIRouter(prefix="/api/v1/webhooks/meta/whatsapp", tags=["Meta WhatsApp webhooks"])
MAX_WEBHOOK_BYTES = 1024 * 1024


def _configured_secret() -> str:
    secret = (settings.meta_whatsapp_app_secret or "").strip()
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="meta_webhook_not_configured")
    return secret


@router.get("")
async def verify_meta_webhook(
    request: Request,
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    """Complete Meta's webhook subscription handshake using a server-side verify token."""
    expected = (settings.meta_whatsapp_webhook_verify_token or "").strip()
    if not expected or len(expected.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="meta_webhook_verification_not_configured")
    if hub_mode != "subscribe" or not hub_verify_token or not hmac.compare_digest(expected, hub_verify_token):
        raise HTTPException(status_code=403, detail="meta_webhook_verification_rejected")
    if not hub_challenge or len(hub_challenge) > 512:
        raise HTTPException(status_code=400, detail="invalid_meta_webhook_challenge")
    return PlainTextResponse(hub_challenge, headers={"Cache-Control": "no-store"})


async def _bounded_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared:
        try:
            size = int(declared)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_content_length") from None
        if size < 0:
            raise HTTPException(status_code=400, detail="invalid_content_length") from None
        if size > MAX_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="payload_too_large")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="payload_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", status_code=202)
async def receive_meta_webhook(request: Request) -> dict[str, object]:
    """Verify Meta's raw-body HMAC signature and persist events idempotently."""
    secret = _configured_secret()
    raw = await _bounded_body(request)
    supplied = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="invalid_meta_webhook_signature")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="invalid_meta_webhook_json") from None
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        raise HTTPException(status_code=422, detail="unsupported_meta_webhook_payload")

    entries = payload.get("entry")
    if not isinstance(entries, list) or len(entries) > 100:
        raise HTTPException(status_code=422, detail="invalid_meta_webhook_entries")
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="webhook_storage_not_configured")
    # One provider payload may contain changes for multiple phone numbers. Split it
    # into independently routable inbox rows so no valid tenant event is lost because
    # a single nullable phone_number_id cannot represent the whole payload.
    grouped: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes", [])
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            metadata = value.get("metadata") if isinstance(value, dict) else None
            phone_id = metadata.get("phone_number_id") if isinstance(metadata, dict) else None
            if not isinstance(phone_id, str) or not phone_id.strip():
                continue
            phone_id = phone_id[:128]
            grouped.setdefault(phone_id, []).append({
                "entry_id": entry.get("id"),
                "change": change,
            })

    event_rows: list[tuple[str | None, str, dict[str, object], str]] = []
    if not grouped:
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        event_rows.append((None, "other", payload, hashlib.sha256(canonical.encode("utf-8")).hexdigest()))
    else:
        for phone_id, changes in grouped.items():
            grouped_entries: dict[str, dict[str, object]] = {}
            kinds: set[str] = set()
            for item in changes:
                entry_id = item.get("entry_id")
                key = str(entry_id) if entry_id is not None else "__entry_without_id__"
                target = grouped_entries.setdefault(key, {"changes": []})
                if entry_id is not None:
                    target["id"] = entry_id
                target_changes = target["changes"]
                change = item["change"]
                target_changes.append(change)  # type: ignore[union-attr]
                value = change.get("value") if isinstance(change, dict) else None
                if isinstance(value, dict):
                    if isinstance(value.get("messages"), list) and value["messages"]:
                        kinds.add("messages")
                    if isinstance(value.get("statuses"), list) and value["statuses"]:
                        kinds.add("statuses")
            scoped_payload: dict[str, object] = {
                "object": payload["object"],
                "entry": list(grouped_entries.values()),
            }
            event_kind = next(iter(kinds)) if len(kinds) == 1 else "other"
            canonical = json.dumps(
                {"phone_number_id": phone_id, "payload": scoped_payload},
                separators=(",", ":"),
                sort_keys=True,
            )
            event_rows.append((
                phone_id, event_kind, scoped_payload,
                hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            ))

    accepted = duplicates = 0
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                for phone_id, event_kind, scoped_payload, payload_hash in event_rows:
                    row = await connection.fetchrow(
                        """INSERT INTO meta_whatsapp_webhook_events
                           (payload_sha256, phone_number_id, event_kind, payload)
                           VALUES ($1,$2,$3,$4::jsonb)
                           ON CONFLICT (payload_sha256) DO NOTHING
                           RETURNING id""",
                        payload_hash, phone_id, event_kind,
                        json.dumps(scoped_payload, separators=(",", ":")),
                    )
                    if row is None:
                        duplicates += 1
                    else:
                        accepted += 1
    except Exception:
        # Do not include raw provider payloads, tokens, or message content in logs/errors.
        raise HTTPException(status_code=503, detail="meta_webhook_persistence_failed") from None
    return {
        "accepted": True,
        "events_accepted": accepted,
        "duplicates": duplicates,
    }
