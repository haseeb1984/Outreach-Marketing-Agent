"""Tenant-scoped SMTP account storage with authenticated encryption at rest."""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_ALLOWED_SMTP_HOSTS = {
    "smtp.gmail.com",
    "smtp.office365.com",
    "smtp-mail.outlook.com",
    "smtp.zoho.com",
    "smtp.zoho.eu",
    "smtp-relay.brevo.com",
    "smtp.sendgrid.net",
    "smtp.mailgun.org",
}
_SES_HOST = re.compile(r"^email-smtp\.[a-z0-9-]+\.amazonaws\.com$")


class CredentialEncryptionNotConfigured(RuntimeError):
    pass


class CredentialDecryptionFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class SMTPAccountConfig:
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from_email: str
    smtp_from_name: str
    smtp_starttls: bool = True
    public_base_url: str | None = None


def _key() -> bytes:
    encoded = settings.provider_credential_encryption_key
    if not isinstance(encoded, str) or not encoded.strip():
        raise CredentialEncryptionNotConfigured("provider_credential_encryption_key_missing")
    value = encoded.strip()
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error):
        raise CredentialEncryptionNotConfigured("provider_credential_encryption_key_invalid") from None
    if len(raw) != 32:
        raise CredentialEncryptionNotConfigured("provider_credential_encryption_key_invalid")
    return raw


def _aad(workspace_id: str, account_id: UUID) -> bytes:
    return ("workspace-email-account:" + workspace_id + ":" + str(account_id)).encode("utf-8")


def _encrypt_password(password: str, workspace_id: str, account_id: UUID) -> bytes:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, password.encode("utf-8"), _aad(workspace_id, account_id))
    return nonce + ciphertext


def _decrypt_password(ciphertext: bytes, workspace_id: str, account_id: UUID) -> str:
    raw = bytes(ciphertext)
    if len(raw) < 29:
        raise CredentialDecryptionFailed("provider_credential_ciphertext_invalid")
    try:
        return AESGCM(_key()).decrypt(raw[:12], raw[12:], _aad(workspace_id, account_id)).decode("utf-8")
    except (InvalidTag, UnicodeDecodeError, ValueError):
        raise CredentialDecryptionFailed("provider_credential_decryption_failed") from None


def _validate_host(host: str) -> str:
    normalized = host.strip().lower().rstrip(".")
    if normalized not in _ALLOWED_SMTP_HOSTS and not _SES_HOST.fullmatch(normalized):
        raise ValueError("smtp_host_not_supported")
    return normalized


def _validate_email(value: str) -> str:
    normalized = value.strip()
    if len(normalized) > 320 or normalized.count("@") != 1 or any(ch.isspace() for ch in normalized):
        raise ValueError("invalid_email_address")
    local, domain = normalized.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        raise ValueError("invalid_email_address")
    return normalized


class SMTPAccountStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create(
        self, *, workspace_id: str, created_by: UUID | str, label: str,
        smtp_host: str, smtp_username: str, smtp_password: str,
        from_email: str, from_name: str,
    ) -> dict[str, Any]:
        label = label.strip()
        if not label or len(label) > 120:
            raise ValueError("invalid_account_label")
        host = _validate_host(smtp_host)
        username = smtp_username.strip()
        if not username or len(username) > 320:
            raise ValueError("invalid_smtp_username")
        if not isinstance(smtp_password, str) or not 1 <= len(smtp_password) <= 1024:
            raise ValueError("invalid_smtp_password")
        sender = _validate_email(from_email)
        name = from_name.strip()
        if not name or len(name) > 200:
            raise ValueError("invalid_sender_name")
        account_id = uuid4()
        encrypted = _encrypt_password(smtp_password, workspace_id, account_id)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO workspace_email_accounts
                   (id,workspace_id,label,smtp_host,smtp_port,smtp_username,encrypted_password,
                    from_email,from_name,starttls,status,created_by)
                   VALUES ($1,$2,$3,$4,587,$5,$6,$7,$8,TRUE,'pending_test',$9)
                   RETURNING id,workspace_id,label,smtp_host,smtp_port,smtp_username,
                             from_email,from_name,starttls,status,created_at,updated_at""",
                account_id, workspace_id, label, host, username, encrypted, sender, name,
                UUID(str(created_by)),
            )
        return self._serialize(dict(row))

    async def list_accounts(self, *, workspace_id: str) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id,workspace_id,label,smtp_host,smtp_port,smtp_username,from_email,
                          from_name,starttls,status,created_at,updated_at
                   FROM workspace_email_accounts WHERE workspace_id=$1
                   ORDER BY created_at DESC,id""",
                workspace_id,
            )
        return [self._serialize(dict(row)) for row in rows]

    async def get_config(self, *, workspace_id: str, account_id: UUID, allow_pending_test: bool = False) -> SMTPAccountConfig:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id,workspace_id,smtp_host,smtp_port,smtp_username,encrypted_password,
                          from_email,from_name,starttls,status
                   FROM workspace_email_accounts WHERE id=$1 AND workspace_id=$2""",
                account_id, workspace_id,
            )
        if row is None or row["status"] not in ({"active", "pending_test"} if allow_pending_test else {"active"}):
            raise LookupError("email_account_not_available")
        password = _decrypt_password(row["encrypted_password"], row["workspace_id"], row["id"])
        return SMTPAccountConfig(
            smtp_host=row["smtp_host"], smtp_port=row["smtp_port"],
            smtp_username=row["smtp_username"], smtp_password=password,
            smtp_from_email=row["from_email"], smtp_from_name=row["from_name"],
            smtp_starttls=row["starttls"], public_base_url=settings.public_base_url,
        )

    async def activate_after_test(self, *, workspace_id: str, account_id: UUID) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE workspace_email_accounts SET status='active',updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND status='pending_test'""",
                account_id, workspace_id,
            )
        return result.endswith(" 1")

    async def disable(self, *, workspace_id: str, account_id: UUID) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE workspace_email_accounts SET status='disabled',updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND status='active'""",
                account_id, workspace_id,
            )
        return result.endswith(" 1")

    @staticmethod
    def _serialize(row: dict[str, Any]) -> dict[str, Any]:
        for key in ("id", "created_by"):
            if row.get(key) is not None:
                row[key] = str(row[key])
        # Encrypted credential bytes are never selected for client-facing lists.
        row.pop("encrypted_password", None)
        return row
