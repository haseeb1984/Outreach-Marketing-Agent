"""Encrypted, tenant-bound WhatsApp inbound media storage and Meta fetcher."""
from __future__ import annotations

import base64
import os
from typing import Any
from uuid import UUID

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.services.whatsapp_credential_store import WhatsAppCredentialStore

MAX_MEDIA_BYTES = 16 * 1024 * 1024
_ALLOWED_MEDIA_TYPES = {
    "image/jpeg", "image/png", "image/webp", "video/mp4", "video/3gpp",
    "audio/aac", "audio/amr", "audio/mpeg", "audio/mp4", "audio/ogg",
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
}
_ALLOWED_MEDIA_HOSTS = {"lookaside.fbsbx.com", "lookaside.facebook.com"}


class WhatsAppMediaError(RuntimeError):
    pass


def _key() -> bytes:
    value = (settings.provider_credential_encryption_key or "").strip()
    if not value:
        raise WhatsAppMediaError("whatsapp_media_encryption_not_configured")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error):
        raise WhatsAppMediaError("whatsapp_media_encryption_not_configured") from None
    if len(raw) != 32:
        raise WhatsAppMediaError("whatsapp_media_encryption_not_configured")
    return raw


def _aad(workspace_id: str, account_id: UUID, message_id: UUID) -> bytes:
    return f"whatsapp-inbound-media:{workspace_id}:{account_id}:{message_id}".encode()


def encrypt_media(data: bytes, workspace_id: str, account_id: UUID, message_id: UUID) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_key()).encrypt(nonce, data, _aad(workspace_id, account_id, message_id))


def decrypt_media(data: bytes, workspace_id: str, account_id: UUID, message_id: UUID) -> bytes:
    raw = bytes(data or b"")
    if len(raw) < 29:
        raise WhatsAppMediaError("whatsapp_media_ciphertext_invalid")
    try:
        return AESGCM(_key()).decrypt(raw[:12], raw[12:], _aad(workspace_id, account_id, message_id))
    except Exception:
        raise WhatsAppMediaError("whatsapp_media_decryption_failed") from None


async def download_meta_media(*, pool: Any, workspace_id: str, account_id: UUID, message_id: UUID) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT m.id,m.media_metadata,m.media_ciphertext,m.media_mime_type,
                      m.media_filename,m.media_size,a.id AS account_id
               FROM whatsapp_inbound_messages m
               JOIN whatsapp_conversations c ON c.id=m.conversation_id
                 AND c.workspace_id=m.workspace_id
               JOIN workspace_whatsapp_accounts a ON a.id=c.account_id
                 AND a.workspace_id=c.workspace_id AND a.status='active'
               WHERE m.id=$1 AND m.workspace_id=$2 AND a.id=$3""",
            message_id, workspace_id, account_id,
        )
    if row is None:
        raise LookupError("whatsapp_media_message_not_found")
    if row["media_ciphertext"] is not None:
        return {"already_downloaded": True, "mime_type": row["media_mime_type"], "size": row["media_size"]}
    metadata = row["media_metadata"]
    if isinstance(metadata, str):
        import json
        metadata = json.loads(metadata)
    media_id = metadata.get("id") if isinstance(metadata, dict) else None
    if not isinstance(media_id, str) or not media_id.isdigit() or len(media_id) > 128:
        raise WhatsAppMediaError("whatsapp_message_has_no_downloadable_media")

    credentials = await WhatsAppCredentialStore(pool).get_active_credentials(
        workspace_id=workspace_id, account_id=account_id,
    )
    version = (settings.meta_graph_api_version or "").strip()
    if not version or not version.startswith("v") or len(version) > 8:
        raise WhatsAppMediaError("meta_graph_api_version_not_configured")
    headers = {"Authorization": "Bearer " + credentials.access_token, "Accept": "application/json"}
    timeout = httpx.Timeout(20.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        info = await client.get(
            f"https://graph.facebook.com/{version}/{media_id}",
            headers=headers,
        )
        if info.status_code != 200:
            raise WhatsAppMediaError("meta_media_metadata_fetch_failed")
        try:
            payload = info.json()
        except ValueError:
            raise WhatsAppMediaError("meta_media_metadata_invalid") from None
        url = payload.get("url") if isinstance(payload, dict) else None
        provider_type = payload.get("mime_type") if isinstance(payload, dict) else None
        if not isinstance(url, str):
            raise WhatsAppMediaError("meta_media_url_missing")
        parsed = httpx.URL(url)
        if (parsed.scheme != "https" or parsed.host not in _ALLOWED_MEDIA_HOSTS
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or parsed.fragment):
            raise WhatsAppMediaError("meta_media_url_not_allowed")
        mime = str(provider_type or metadata.get("mime_type") or "").split(";")[0].strip().lower()
        if mime not in _ALLOWED_MEDIA_TYPES:
            raise WhatsAppMediaError("whatsapp_media_mime_type_not_allowed")
        content = bytearray()
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code != 200:
                raise WhatsAppMediaError("meta_media_download_failed")
            declared = response.headers.get("content-length")
            if declared:
                try:
                    if int(declared) > MAX_MEDIA_BYTES:
                        raise WhatsAppMediaError("whatsapp_media_too_large")
                except ValueError:
                    raise WhatsAppMediaError("meta_media_length_invalid") from None
            response_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if response_type and response_type != mime:
                raise WhatsAppMediaError("meta_media_content_type_mismatch")
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_MEDIA_BYTES:
                    raise WhatsAppMediaError("whatsapp_media_too_large")
    if not content:
        raise WhatsAppMediaError("whatsapp_media_empty")
    encrypted = encrypt_media(bytes(content), workspace_id, account_id, message_id)
    filename = metadata.get("filename") if isinstance(metadata, dict) else None
    if not isinstance(filename, str) or not filename.strip():
        extension = mime.split("/")[-1].replace("jpeg", "jpg")
        filename = f"whatsapp-{message_id}.{extension}"
    filename = "".join(ch for ch in filename if ch.isalnum() or ch in "._-")[:180] or f"whatsapp-{message_id}"
    async with pool.acquire() as conn:
        saved = await conn.fetchrow(
            """UPDATE whatsapp_inbound_messages m
               SET media_ciphertext=$4,media_mime_type=$5,media_filename=$6,media_size=$7,
                   media_downloaded_at=now()
               FROM whatsapp_conversations c
               WHERE m.id=$1 AND m.workspace_id=$2 AND c.id=m.conversation_id
                 AND c.workspace_id=m.workspace_id AND c.account_id=$3
                 AND m.media_ciphertext IS NULL
               RETURNING m.media_size""",
            message_id, workspace_id, account_id, encrypted, mime, filename, len(content),
        )
    if saved is None:
        return {"already_downloaded": True, "size": len(content)}
    return {"already_downloaded": False, "mime_type": mime, "size": len(content), "filename": filename}
