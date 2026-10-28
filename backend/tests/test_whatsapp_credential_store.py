from __future__ import annotations

import asyncio
import base64
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.services.whatsapp_credential_store import (
    WhatsAppCredentialStore, WhatsAppCredentialUnavailable,
    _aad, decrypt_access_token,
)


def encrypted(token: str, key: bytes, workspace: str, account_id) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, token.encode(), _aad(workspace, account_id))


class FakeConn:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.args = None

    async def fetchrow(self, query, *args):
        self.query, self.args = query, args
        return self.row


class FakePool:
    def __init__(self, row):
        self.conn = FakeConn(row)

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


def setup_key(monkeypatch):
    key = bytes(range(32))
    monkeypatch.setattr(settings, "provider_credential_encryption_key", base64.urlsafe_b64encode(key).decode())
    return key


def test_decrypts_token_with_workspace_account_authenticated_data(monkeypatch):
    key = setup_key(monkeypatch)
    account = uuid4()
    ciphertext = encrypted("EAAB.test-token", key, "workspace-a", account)
    assert decrypt_access_token(ciphertext, "workspace-a", account) == "EAAB.test-token"


def test_wrong_workspace_fails_closed(monkeypatch):
    key = setup_key(monkeypatch)
    account = uuid4()
    ciphertext = encrypted("EAAB.test-token", key, "workspace-a", account)
    with pytest.raises(WhatsAppCredentialUnavailable, match="decryption_failed"):
        decrypt_access_token(ciphertext, "workspace-b", account)


def test_wrong_account_fails_closed(monkeypatch):
    key = setup_key(monkeypatch)
    account = uuid4()
    ciphertext = encrypted("EAAB.test-token", key, "workspace-a", account)
    with pytest.raises(WhatsAppCredentialUnavailable, match="decryption_failed"):
        decrypt_access_token(ciphertext, "workspace-a", uuid4())


def test_missing_encryption_key_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "provider_credential_encryption_key", None)
    with pytest.raises(WhatsAppCredentialUnavailable, match="key_not_configured"):
        decrypt_access_token(b"x" * 40, "workspace-a", uuid4())


@pytest.mark.parametrize("key_value", ["bad key!!!", base64.b64encode(b"short").decode()])
def test_invalid_encryption_key_fails_closed(monkeypatch, key_value):
    monkeypatch.setattr(settings, "provider_credential_encryption_key", key_value)
    with pytest.raises(WhatsAppCredentialUnavailable, match="key_invalid"):
        decrypt_access_token(b"x" * 40, "workspace-a", uuid4())


@pytest.mark.parametrize("ciphertext", [b"", b"too-short", None])
def test_invalid_ciphertext_fails_closed(monkeypatch, ciphertext):
    setup_key(monkeypatch)
    with pytest.raises(WhatsAppCredentialUnavailable, match="ciphertext_invalid"):
        decrypt_access_token(ciphertext, "workspace-a", uuid4())


def test_tampered_ciphertext_fails_closed(monkeypatch):
    key = setup_key(monkeypatch)
    account = uuid4()
    ciphertext = bytearray(encrypted("EAAB.test-token", key, "workspace-a", account))
    ciphertext[-1] ^= 1
    with pytest.raises(WhatsAppCredentialUnavailable, match="decryption_failed"):
        decrypt_access_token(bytes(ciphertext), "workspace-a", account)


def test_resolver_only_queries_active_tenant_account_and_returns_no_ciphertext(monkeypatch):
    key = setup_key(monkeypatch)
    account, workspace = uuid4(), "workspace-a"
    row = {
        "id": account, "workspace_id": workspace, "waba_id": "123456789",
        "phone_number_id": "987654321", "encrypted_access_token": encrypted("EAAB.test-token", key, workspace, account),
    }
    pool = FakePool(row)
    result = asyncio.run(WhatsAppCredentialStore(pool).get_active_credentials(
        workspace_id=workspace, account_id=account,
    ))
    assert result.access_token == "EAAB.test-token"
    assert result.phone_number_id == "987654321"
    assert result.waba_id == "123456789"
    assert "status='active'" in pool.conn.query
    assert "workspace_id=$2" in pool.conn.query
    assert pool.conn.args == (account, workspace)
    assert not hasattr(result, "encrypted_access_token")


def test_missing_or_inactive_account_does_not_decrypt(monkeypatch):
    setup_key(monkeypatch)
    with pytest.raises(WhatsAppCredentialUnavailable, match="not_active_or_credentials_missing"):
        asyncio.run(WhatsAppCredentialStore(FakePool(None)).get_active_credentials(
            workspace_id="workspace-a", account_id=uuid4(),
        ))


def test_invalid_workspace_is_rejected_before_database_access():
    pool = FakePool(None)
    with pytest.raises(ValueError, match="workspace_id_invalid"):
        asyncio.run(WhatsAppCredentialStore(pool).get_active_credentials(
            workspace_id=" ", account_id=uuid4(),
        ))
    assert pool.conn.query is None


def test_invalid_asset_ids_fail_closed(monkeypatch):
    key = setup_key(monkeypatch)
    account, workspace = uuid4(), "workspace-a"
    row = {
        "id": account, "workspace_id": workspace, "waba_id": "waba-not-numeric",
        "phone_number_id": "987654321", "encrypted_access_token": encrypted("EAAB.test-token", key, workspace, account),
    }
    with pytest.raises(WhatsAppCredentialUnavailable, match="asset_id_invalid"):
        asyncio.run(WhatsAppCredentialStore(FakePool(row)).get_active_credentials(
            workspace_id=workspace, account_id=account,
        ))
