from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.email_account_routes import EmailAccountUpdate
from app.services import smtp_account_store
from app.services.smtp_account_store import SMTPAccountStore


def test_email_account_update_requires_tls_and_rejects_extra_fields():
    base = {
        "workspace_id": "workspace-a", "label": "Primary", "smtp_host": "smtp.gmail.com",
        "smtp_username": "sender@example.com", "smtp_password": "rotated-secret",
        "from_email": "sender@example.com", "from_name": "Sender",
    }
    assert EmailAccountUpdate(**base).smtp_port == 587
    with pytest.raises(ValidationError):
        EmailAccountUpdate(**{**base, "smtp_port": 465})
    with pytest.raises(ValidationError):
        EmailAccountUpdate(**{**base, "starttls": False})
    with pytest.raises(ValidationError):
        EmailAccountUpdate(**{**base, "auto_send": True})


class FakeConnection:
    def __init__(self):
        self.args = None
        self.query = None

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, query, *args):
        self.query, self.args = query, args
        return {
            "id": args[0], "workspace_id": args[1], "label": args[2],
            "smtp_host": args[3], "smtp_port": 587, "smtp_username": args[4],
            "from_email": args[6], "from_name": args[7], "starttls": True,
            "status": "pending_test",
        }


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


@pytest.mark.asyncio
async def test_rotating_credentials_resets_account_to_pending_test(monkeypatch):
    account_id = uuid4()
    connection = FakeConnection()
    monkeypatch.setattr(smtp_account_store, "_encrypt_password", lambda password, workspace, account: b"x" * 32)
    result = await SMTPAccountStore(FakePool(connection)).update(
        workspace_id="workspace-a", account_id=account_id, label="Primary",
        smtp_host="smtp.gmail.com", smtp_username="sender@example.com",
        smtp_password="new-secret", from_email="sender@example.com", from_name="Sender",
    )
    assert result["status"] == "pending_test"
    assert "status='pending_test'" in connection.query
    assert "WHERE id=$1 AND workspace_id=$2" in connection.query
    assert connection.args[0:2] == (account_id, "workspace-a")
    assert connection.args[5] == b"x" * 32
    assert "new-secret" not in repr(result)


@pytest.mark.asyncio
async def test_rotating_credentials_does_not_update_disabled_account(monkeypatch):
    account_id = uuid4()
    connection = FakeConnection()
    async def no_row(query, *args):
        connection.query, connection.args = query, args
        return None
    connection.fetchrow = no_row
    monkeypatch.setattr(smtp_account_store, "_encrypt_password", lambda password, workspace, account: b"x" * 32)
    result = await SMTPAccountStore(FakePool(connection)).update(
        workspace_id="workspace-a", account_id=account_id, label="Primary",
        smtp_host="smtp.gmail.com", smtp_username="sender@example.com",
        smtp_password="new-secret", from_email="sender@example.com", from_name="Sender",
    )
    assert result is None
    assert "status IN ('active','pending_test')" in connection.query
