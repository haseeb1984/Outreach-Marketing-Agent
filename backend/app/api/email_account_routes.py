"""Workspace-scoped SMTP account management; credentials are never returned to clients."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.services.email_delivery import EmailDeliveryFailed, EmailDeliveryNotConfigured, SMTPEmailDelivery
from app.services.smtp_account_store import (
    CredentialDecryptionFailed,
    CredentialEncryptionNotConfigured,
    SMTPAccountStore,
)

router = APIRouter(prefix="/api/v1/integrations/email-accounts", tags=["email accounts"])


class EmailAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=120)
    smtp_host: str = Field(min_length=3, max_length=253)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = Field(min_length=1, max_length=320)
    smtp_password: str = Field(min_length=1, max_length=1024)
    from_email: str = Field(min_length=3, max_length=320)
    from_name: str = Field(default="Outreach Marketing Agent", min_length=1, max_length=200)
    starttls: bool = True

    @field_validator("smtp_port")
    @classmethod
    def require_starttls_port(cls, value: int) -> int:
        if value != 587:
            raise ValueError("smtp_starttls_port_required")
        return value

    @field_validator("starttls")
    @classmethod
    def require_starttls(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("smtp_tls_required")
        return value


def _store(request: Request) -> SMTPAccountStore:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="email_account_service_not_configured")
    return SMTPAccountStore(pool)


async def _authorize(request: Request, workspace_id: str, role: str, *, csrf: bool = False) -> dict:
    _, _, session = await _authenticated(request)
    if csrf:
        _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    return session


@router.get("")
async def list_email_accounts(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    await _authorize(request, workspace_id, "viewer")
    try:
        return {"items": await _store(request).list_accounts(workspace_id=workspace_id)}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="email_account_list_unavailable") from None


@router.post("", status_code=201)
async def create_email_account(payload: EmailAccountCreate, request: Request) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin")
    if payload.starttls is not True or payload.smtp_port != 587:
        raise HTTPException(status_code=422, detail="smtp_tls_required")
    try:
        item = await _store(request).create(
            workspace_id=payload.workspace_id,
            created_by=session["user_id"],
            label=payload.label,
            smtp_host=payload.smtp_host,
            smtp_username=payload.smtp_username,
            smtp_password=payload.smtp_password,
            from_email=payload.from_email,
            from_name=payload.from_name,
        )
        return item
    except CredentialEncryptionNotConfigured:
        raise HTTPException(status_code=503, detail="provider_credential_encryption_not_configured") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception as exc:
        if type(exc).__name__ == "UniqueViolationError":
            raise HTTPException(status_code=409, detail="email_account_label_already_exists") from None
        raise HTTPException(status_code=503, detail="email_account_create_unavailable") from None


@router.post("/{account_id}/test")
async def test_email_account(account_id: UUID, request: Request, workspace_id: str = Query(min_length=1, max_length=200)) -> dict:
    await _authorize(request, workspace_id, "admin", csrf=True)
    try:
        store = _store(request)
        configuration = await store.get_config(workspace_id=workspace_id, account_id=account_id, allow_pending_test=True)
        await SMTPEmailDelivery(configuration).test_connection()
        await store.activate_after_test(workspace_id=workspace_id, account_id=account_id)
        return {"workspace_id": workspace_id, "account_id": str(account_id), "ok": True,
                "message": "SMTP TLS connection and authentication succeeded. No email was sent."}
    except LookupError:
        raise HTTPException(status_code=404, detail="email_account_not_available") from None
    except CredentialEncryptionNotConfigured:
        raise HTTPException(status_code=503, detail="provider_credential_encryption_not_configured") from None
    except CredentialDecryptionFailed:
        raise HTTPException(status_code=503, detail="provider_credential_decryption_failed") from None
    except EmailDeliveryNotConfigured:
        raise HTTPException(status_code=503, detail="email_account_configuration_incomplete") from None
    except EmailDeliveryFailed:
        raise HTTPException(status_code=502, detail="email_account_connection_failed") from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="email_account_test_unavailable") from None


@router.delete("/{account_id}")
async def disable_email_account(account_id: UUID, request: Request, workspace_id: str = Query(min_length=1, max_length=200)) -> dict:
    await _authorize(request, workspace_id, "admin", csrf=True)
    try:
        disabled = await _store(request).disable(workspace_id=workspace_id, account_id=account_id)
    except Exception:
        raise HTTPException(status_code=503, detail="email_account_disable_unavailable") from None
    if not disabled:
        raise HTTPException(status_code=404, detail="email_account_not_available")
    return {"workspace_id": workspace_id, "account_id": str(account_id), "disabled": True}
