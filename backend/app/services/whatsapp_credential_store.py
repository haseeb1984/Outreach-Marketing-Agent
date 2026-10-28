"""Tenant-scoped resolver for verified WhatsApp account credentials.

Credentials are decrypted only for active accounts and are never serialized or logged.
This service does not send messages or bypass outbound eligibility policy.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


class WhatsAppCredentialUnavailable(RuntimeError):
    """Credentials are missing, inactive, or cannot be safely decrypted."""


@dataclass(frozen=True)
class WhatsAppAccountCredentials:
    workspace_id: str
    account_id: UUID
    phone_number_id: str
    waba_id: str
    access_token: str


def _key() -> bytes:
    encoded = settings.provider_credential_encryption_key
    if not isinstance(encoded, str) or not encoded.strip():
        raise WhatsAppCredentialUnavailable("whatsapp_credential_key_not_configured")
    value = encoded.strip()
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error):
        raise WhatsAppCredentialUnavailable("whatsapp_credential_key_invalid") from None
    if len(raw) != 32:
        raise WhatsAppCredentialUnavailable("whatsapp_credential_key_invalid")
    return raw


def _aad(workspace_id: str, account_id: UUID) -> bytes:
    return ("workspace-whatsapp-account:" + workspace_id + ":" + str(account_id)).encode("utf-8")


def decrypt_access_token(ciphertext: bytes, workspace_id: str, account_id: UUID) -> str:
    """Decrypt the existing account format; tenant/account IDs are authenticated as AAD."""
    try:
        raw = bytes(ciphertext)
    except (TypeError, ValueError):
        raise WhatsAppCredentialUnavailable("whatsapp_credential_ciphertext_invalid") from None
    if len(raw) < 29:
        raise WhatsAppCredentialUnavailable("whatsapp_credential_ciphertext_invalid")
    try:
        token = AESGCM(_key()).decrypt(raw[:12], raw[12:], _aad(workspace_id, account_id)).decode("utf-8")
    except (InvalidTag, UnicodeDecodeError, ValueError):
        raise WhatsAppCredentialUnavailable("whatsapp_credential_decryption_failed") from None
    if not token or any(char.isspace() for char in token):
        raise WhatsAppCredentialUnavailable("whatsapp_credential_value_invalid")
    return token


class WhatsAppCredentialStore:
    """Read active, tenant-scoped account credentials without exposing ciphertext."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def get_active_credentials(
        self, *, workspace_id: str, account_id: UUID,
    ) -> WhatsAppAccountCredentials:
        if not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200:
            raise ValueError("workspace_id_invalid")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, workspace_id, waba_id, phone_number_id, encrypted_access_token
                   FROM workspace_whatsapp_accounts
                   WHERE id=$1 AND workspace_id=$2 AND status='active'
                     AND encrypted_access_token IS NOT NULL""",
                account_id, workspace_id,
            )
        if row is None:
            raise WhatsAppCredentialUnavailable("whatsapp_account_not_active_or_credentials_missing")
        token = decrypt_access_token(row["encrypted_access_token"], row["workspace_id"], row["id"])
        phone_number_id = str(row["phone_number_id"] or "")
        waba_id = str(row["waba_id"] or "")
        if not phone_number_id.isdigit() or not waba_id.isdigit():
            raise WhatsAppCredentialUnavailable("whatsapp_account_asset_id_invalid")
        return WhatsAppAccountCredentials(
            workspace_id=str(row["workspace_id"]), account_id=row["id"],
            phone_number_id=phone_number_id, waba_id=waba_id, access_token=token,
        )
