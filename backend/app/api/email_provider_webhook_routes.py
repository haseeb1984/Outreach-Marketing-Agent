"""Signed, provider-neutral email feedback webhook.

A provider-specific relay normalizes vendor callbacks into this small contract and
forwards them with X-Email-Event-Signature. Workspace identity is derived from the
persisted delivery, never trusted from the callback body.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import UUID
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.services.email_provider_event_store import EmailProviderEventStore

router = APIRouter(prefix="/api/v1/webhooks/email", tags=["email provider events"])
MAX_BODY_BYTES = 64 * 1024


class EmailProviderEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    event_id: str = Field(min_length=1, max_length=300)
    delivery_id: UUID
    event_type: str = Field(pattern=r"^(delivered|deferred|bounced|complained|unsubscribed)$")
    recipient: str = Field(min_length=3, max_length=320)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone_required")
        return value


def expected_signature(raw: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


@router.post("/events", status_code=202)
async def ingest_email_provider_event(
    request: Request,
    x_email_event_signature: str | None = Header(default=None, alias="X-Email-Event-Signature"),
):
    secret = (settings.outreach_webhook_secret or "").strip()
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="email_event_webhook_not_configured")
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) < 0:
                raise ValueError
            if int(declared) > MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="payload_too_large")
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_content_length") from None
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="payload_too_large")
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not x_email_event_signature or not hmac.compare_digest(
        expected_signature(raw, secret), x_email_event_signature
    ):
        raise HTTPException(status_code=401, detail="invalid_email_event_signature")
    try:
        event = EmailProviderEvent.model_validate(json.loads(raw))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="invalid_email_provider_event") from None

    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="email_event_store_not_configured")
    try:
        return await EmailProviderEventStore(pool).ingest(
            provider=event.provider,
            event_id=event.event_id,
            delivery_id=event.delivery_id,
            event_type=event.event_type,
            recipient=event.recipient,
            occurred_at=event.occurred_at.astimezone(timezone.utc),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="email_delivery_not_found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="email_provider_event_unavailable") from None


@router.post("/unsubscribe", status_code=200)
async def one_click_unsubscribe(request: Request):
    """RFC 8058 one-click unsubscribe using a signed, recipient-specific opaque token."""
    secret = (settings.outreach_webhook_secret or "").strip()
    token = request.query_params.get("token", "")
    if len(secret.encode("utf-8")) < 32 or len(token) > 4096 or "." not in token:
        raise HTTPException(status_code=400, detail="unsubscribe_token_invalid")
    encoded, supplied_signature = token.rsplit(".", 1)
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied_signature):
            raise ValueError
        workspace_id, prospect_raw, email = payload.decode("utf-8").split("\\n", 2)
        prospect_id = UUID(prospect_raw)
        if not workspace_id or len(workspace_id) > 200 or not email or len(email) > 320:
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="unsubscribe_token_invalid") from None
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="email_unsubscribe_unavailable")
    try:
        return await EmailProviderEventStore(pool).unsubscribe(
            workspace_id=workspace_id,
            prospect_id=prospect_id,
            email=email,
            occurred_at=datetime.now(timezone.utc),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="unsubscribe_contact_not_found") from None
    except Exception:
        raise HTTPException(status_code=503, detail="email_unsubscribe_unavailable") from None
