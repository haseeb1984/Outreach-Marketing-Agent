"""Workspace-scoped official Meta WhatsApp account registry.

Access tokens are encrypted with the same environment-managed 32-byte key used for
provider credentials. Newly added accounts remain pending verification; this module
does not enable outbound sends or return tokens to clients.
"""
from __future__ import annotations

import base64
import json
import os
import re
from uuid import UUID, uuid4

import httpx
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings

router = APIRouter(prefix="/api/v1/integrations/whatsapp/accounts", tags=["WhatsApp accounts"])
_META_ID = re.compile(r"^[0-9]{5,128}$")


def _key() -> bytes:
    encoded = settings.provider_credential_encryption_key
    if not isinstance(encoded, str) or not encoded.strip():
        raise HTTPException(status_code=503, detail="provider_credential_encryption_not_configured")
    value = encoded.strip()
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error):
        raise HTTPException(status_code=503, detail="provider_credential_encryption_not_configured") from None
    if len(raw) != 32:
        raise HTTPException(status_code=503, detail="provider_credential_encryption_not_configured")
    return raw


def _encrypt(token: str, workspace_id: str, account_id: UUID) -> bytes:
    nonce = os.urandom(12)
    aad = ("workspace-whatsapp-account:" + workspace_id + ":" + str(account_id)).encode()
    return nonce + AESGCM(_key()).encrypt(nonce, token.encode("utf-8"), aad)


def _decrypt(ciphertext: bytes, workspace_id: str, account_id: UUID) -> str:
    raw = bytes(ciphertext)
    if len(raw) < 29:
        raise HTTPException(status_code=503, detail="whatsapp_credential_decryption_failed")
    aad = ("workspace-whatsapp-account:" + workspace_id + ":" + str(account_id)).encode()
    try:
        return AESGCM(_key()).decrypt(raw[:12], raw[12:], aad).decode("utf-8")
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_credential_decryption_failed") from None


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="whatsapp_account_service_not_configured")
    return pool


async def _authorize(request: Request, workspace_id: str, role: str, session: dict) -> None:
    auth = getattr(request.app.state, "auth_store", None)
    if auth is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth.authorize_workspace(user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role):
        raise HTTPException(status_code=404, detail="workspace_not_found")


class WhatsAppAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=120)
    waba_id: str = Field(min_length=5, max_length=128)
    phone_number_id: str = Field(min_length=5, max_length=128)
    access_token: str = Field(min_length=20, max_length=4096)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("whatsapp_account_label_required")
        return value

    @field_validator("waba_id", "phone_number_id")
    @classmethod
    def validate_meta_ids(cls, value: str) -> str:
        value = value.strip()
        if not _META_ID.fullmatch(value):
            raise ValueError("invalid_meta_asset_id")
        return value

    @field_validator("access_token")
    @classmethod
    def clean_token(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ch.isspace() for ch in value):
            raise ValueError("invalid_meta_access_token")
        return value


@router.get("")
async def list_whatsapp_accounts(request: Request, workspace_id: str = Query(min_length=1, max_length=200)) -> dict[str, Any]:
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    try:
        async with _pool(request).acquire() as connection:
            rows = await connection.fetch(
                """SELECT id, workspace_id, label, waba_id, phone_number_id, status, created_at, updated_at
                   FROM workspace_whatsapp_accounts WHERE workspace_id=$1
                   ORDER BY created_at DESC LIMIT 100""",
                workspace_id,
            )
        return {"items": [
            {**dict(row), "id": str(row["id"]), "workspace_id": str(row["workspace_id"])}
            for row in rows
        ]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_account_list_unavailable") from None


@router.post("", status_code=201)
async def create_whatsapp_account(payload: WhatsAppAccountCreate, request: Request) -> dict[str, Any]:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    account_id = uuid4()
    encrypted = _encrypt(payload.access_token, payload.workspace_id, account_id)
    try:
        async with _pool(request).acquire() as connection:
            row = await connection.fetchrow(
                """INSERT INTO workspace_whatsapp_accounts
                   (id, workspace_id, label, waba_id, phone_number_id, encrypted_access_token, created_by)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)
                   RETURNING id, workspace_id, label, waba_id, phone_number_id, status, created_at, updated_at""",
                account_id, payload.workspace_id, payload.label, payload.waba_id,
                payload.phone_number_id, encrypted, UUID(str(session["user_id"])),
            )
        return {**dict(row), "id": str(row["id"]), "workspace_id": str(row["workspace_id"]),
                "notice": "Credentials encrypted. Account remains pending verification; WhatsApp sending is disabled."}
    except HTTPException:
        raise
    except Exception as exc:
        if type(exc).__name__ == "UniqueViolationError":
            raise HTTPException(status_code=409, detail="whatsapp_account_or_phone_already_registered") from None
        raise HTTPException(status_code=503, detail="whatsapp_account_create_unavailable") from None


@router.post("/{account_id}/verify")
async def verify_whatsapp_account(
    account_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict[str, Any]:
    """Verify that Meta recognizes this token, phone-number ID and WABA relationship."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin", session)
    version = (settings.meta_graph_api_version or "").strip()
    if not re.fullmatch(r"v[0-9]{2,3}\.0", version):
        raise HTTPException(status_code=503, detail="meta_graph_api_version_not_configured")
    try:
        async with _pool(request).acquire() as connection:
            row = await connection.fetchrow(
                """SELECT waba_id, phone_number_id, encrypted_access_token, status
                   FROM workspace_whatsapp_accounts WHERE id=$1 AND workspace_id=$2""",
                account_id, workspace_id,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="whatsapp_account_not_found")
        if row["status"] == "disabled":
            raise HTTPException(status_code=409, detail="whatsapp_account_disabled")
        token = _decrypt(row["encrypted_access_token"], workspace_id, account_id)
        headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        base = "https://graph.facebook.com/" + version
        timeout = httpx.Timeout(8.0, connect=4.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            phone_response = await client.get(
                base + "/" + row["phone_number_id"],
                params={"fields": "id,display_phone_number,verified_name"},
                headers=headers,
            )
            if phone_response.status_code != 200:
                raise HTTPException(status_code=422, detail="meta_phone_number_verification_failed")
            phone_data = phone_response.json()
            if not isinstance(phone_data, dict) or phone_data.get("id") != row["phone_number_id"]:
                raise HTTPException(status_code=422, detail="meta_phone_number_id_mismatch")
            waba_response = await client.get(
                base + "/" + row["waba_id"] + "/phone_numbers",
                params={"fields": "id", "limit": "100"},
                headers=headers,
            )
            if waba_response.status_code != 200:
                raise HTTPException(status_code=422, detail="meta_waba_verification_failed")
            waba_data = waba_response.json()
            phone_items = waba_data.get("data", []) if isinstance(waba_data, dict) else []
            if not isinstance(phone_items, list) or not any(
                isinstance(item, dict) and item.get("id") == row["phone_number_id"]
                for item in phone_items
            ):
                raise HTTPException(status_code=422, detail="meta_phone_not_in_waba")
            # Meta will not deliver WABA events until this app is subscribed.
            subscription_response = await client.post(
                base + "/" + row["waba_id"] + "/subscribed_apps",
                headers=headers,
            )
            if subscription_response.status_code not in (200, 201):
                raise HTTPException(status_code=422, detail="meta_waba_app_subscription_failed")
            subscription_data = subscription_response.json()
            if not isinstance(subscription_data, dict) or subscription_data.get("success") is not True:
                raise HTTPException(status_code=502, detail="meta_waba_app_subscription_unconfirmed")
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="meta_verification_unavailable") from None
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_account_verification_unavailable") from None

    # Do not let a successful check of an old token activate a concurrently rotated
    # credential. Compare the encrypted snapshot atomically after the Meta round-trip.
    async with _pool(request).acquire() as connection:
        activated = await connection.fetchrow(
            """UPDATE workspace_whatsapp_accounts SET status='active', updated_at=now()
               WHERE id=$1 AND workspace_id=$2 AND status <> 'disabled'
                 AND encrypted_access_token=$3
               RETURNING id""",
            account_id, workspace_id, row["encrypted_access_token"],
        )
    if activated is None:
        raise HTTPException(
            status_code=409,
            detail="whatsapp_account_credentials_changed_during_verification",
        )
    return {
        "verified": True,
        "account_id": str(account_id),
        "status": "active",
        "display_phone_number": phone_data.get("display_phone_number"),
        "verified_name": phone_data.get("verified_name"),
        "webhooks_subscribed": True,
        "notice": "Meta phone/WABA ownership was verified and this app was subscribed to WABA webhooks. Sending remains separately gated by dispatch configuration, consent, approved templates and quota.",
    }


@router.delete("/{account_id}")
async def disable_whatsapp_account(
    account_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict[str, Any]:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin", session)
    try:
        async with _pool(request).acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """UPDATE workspace_whatsapp_accounts SET status='disabled', encrypted_access_token=NULL, updated_at=now()
                       WHERE id=$1 AND workspace_id=$2 AND status <> 'disabled'
                       RETURNING id""",
                    account_id, workspace_id,
                )
                if row is not None:
                    await connection.execute(
                        """WITH cancelled AS (
                               UPDATE whatsapp_outbound_deliveries
                               SET status='cancelled', error_code='whatsapp_account_disabled', updated_at=now()
                               WHERE workspace_id=$1 AND account_id=$2 AND status='queued'
                               RETURNING usage_reservation_id
                           )
                           UPDATE feature_usage_reservations AS u
                           SET status='released', updated_at=now()
                           FROM cancelled AS q
                           WHERE u.id=q.usage_reservation_id
                             AND u.workspace_id=$1 AND u.status='reserved'""",
                        workspace_id, account_id,
                    )
        if row is None:
            raise HTTPException(status_code=404, detail="whatsapp_account_not_found")
        return {"disabled": True, "account_id": str(account_id), "queued_deliveries_cancelled": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_account_disable_unavailable") from None


class WhatsAppTokenRotate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    access_token: str = Field(min_length=20, max_length=4096)

    @field_validator("access_token")
    @classmethod
    def clean_token(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ch.isspace() for ch in value):
            raise ValueError("invalid_meta_access_token")
        return value


@router.post("/{account_id}/rotate-token")
async def rotate_whatsapp_account_token(
    account_id: UUID, payload: WhatsAppTokenRotate, request: Request,
) -> dict[str, Any]:
    """Replace an expiring/revoked token and force fresh Meta verification."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    encrypted = _encrypt(payload.access_token, payload.workspace_id, account_id)
    try:
        async with _pool(request).acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """UPDATE workspace_whatsapp_accounts
                       SET encrypted_access_token=$3,status='pending',updated_at=now()
                       WHERE id=$1 AND workspace_id=$2 AND status <> 'disabled'
                       RETURNING id""",
                    account_id, payload.workspace_id, encrypted,
                )
                if row is None:
                    raise HTTPException(status_code=404, detail="whatsapp_account_not_found")
                cancelled = await connection.fetch(
                    """WITH changed AS (
                           UPDATE whatsapp_outbound_deliveries
                           SET status='cancelled',error_code='whatsapp_token_rotated',updated_at=now()
                           WHERE workspace_id=$1 AND account_id=$2 AND status='queued'
                           RETURNING usage_reservation_id
                       )
                       UPDATE feature_usage_reservations r
                       SET status='released',updated_at=now()
                       FROM changed c
                       WHERE r.id=c.usage_reservation_id AND r.workspace_id=$1
                         AND r.status='reserved'
                       RETURNING r.id""",
                    payload.workspace_id, account_id,
                )
        return {
            "account_id": str(account_id),
            "status": "pending",
            "queued_reservations_released": len(cancelled),
            "notice": "Token replaced and encrypted. Verify the account again to re-check Meta access and WABA webhook subscription before queueing sends.",
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_token_rotation_unavailable") from None


@router.get("/{account_id}/templates")
async def list_whatsapp_templates(
    account_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict[str, Any]:
    """List the synchronized template catalogue without exposing provider credentials."""
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    try:
        async with _pool(request).acquire() as connection:
            account = await connection.fetchrow(
                """SELECT id FROM workspace_whatsapp_accounts
                   WHERE id=$1 AND workspace_id=$2""",
                account_id, workspace_id,
            )
            if account is None:
                raise HTTPException(status_code=404, detail="whatsapp_account_not_found")
            rows = await connection.fetch(
                """SELECT template_name, language_code, category, status,
                          provider_status, components, verified_at, updated_at
                   FROM whatsapp_message_templates
                   WHERE workspace_id=$1 AND account_id=$2
                   ORDER BY template_name, language_code
                   LIMIT 500""",
                workspace_id, account_id,
            )
        return {"items": [dict(row) for row in rows]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_template_list_unavailable") from None


@router.post("/{account_id}/templates/sync")
async def sync_whatsapp_templates(
    account_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict[str, Any]:
    """Import the current Meta template catalogue for an active workspace account.

    Meta pagination is followed only on the exact Graph API host and WABA endpoint.
    Provider credentials never enter query strings, logs, or the response.
    """
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin", session)
    version = (settings.meta_graph_api_version or "").strip()
    if not re.fullmatch(r"v[0-9]{2,3}\.0", version):
        raise HTTPException(status_code=503, detail="meta_graph_api_version_not_configured")

    try:
        async with _pool(request).acquire() as connection:
            account = await connection.fetchrow(
                """SELECT waba_id, encrypted_access_token, status
                   FROM workspace_whatsapp_accounts
                   WHERE id=$1 AND workspace_id=$2""",
                account_id, workspace_id,
            )
        if account is None:
            raise HTTPException(status_code=404, detail="whatsapp_account_not_found")
        if account["status"] != "active" or account["encrypted_access_token"] is None:
            raise HTTPException(status_code=409, detail="whatsapp_account_not_active")
        token = _decrypt(account["encrypted_access_token"], workspace_id, account_id)
        base = "https://graph.facebook.com/" + version
        endpoint = base + "/" + account["waba_id"] + "/message_templates"
        headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        timeout = httpx.Timeout(12.0, connect=4.0)
        templates: list[dict[str, Any]] = []
        next_url: str | None = endpoint
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            for _ in range(20):
                if next_url is None:
                    break
                parsed = httpx.URL(next_url)
                expected = httpx.URL(endpoint)
                if (
                    parsed.scheme != "https"
                    or parsed.host != "graph.facebook.com"
                    or parsed.port not in (None, 443)
                    or parsed.path != expected.path
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.fragment
                ):
                    raise HTTPException(status_code=502, detail="meta_template_pagination_url_invalid")
                response = await client.get(
                    next_url,
                    params={"fields": "id,name,language,status,category,components", "limit": "100"} if next_url == endpoint else None,
                    headers=headers,
                )
                if response.status_code != 200:
                    raise HTTPException(status_code=502, detail="meta_template_sync_unavailable")
                body = response.json()
                if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                    raise HTTPException(status_code=502, detail="meta_template_response_invalid")
                for item in body["data"]:
                    if isinstance(item, dict):
                        templates.append(item)
                paging = body.get("paging")
                next_value = paging.get("next") if isinstance(paging, dict) else None
                if next_value is not None and not isinstance(next_value, str):
                    raise HTTPException(status_code=502, detail="meta_template_pagination_invalid")
                next_url = next_value
            else:
                if next_url is not None:
                    raise HTTPException(status_code=502, detail="meta_template_pagination_limit_exceeded")
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="meta_template_sync_unavailable") from None
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_template_sync_unavailable") from None

    status_map = {
        "APPROVED": "approved",
        "REJECTED": "rejected",
        "PAUSED": "paused",
        "PENDING": "pending",
        "IN_APPEAL": "pending",
        "PENDING_DELETION": "pending",
        "DELETED": "pending",
        "DISABLED": "paused",
    }
    synced = 0
    skipped = 0
    try:
        async with _pool(request).acquire() as connection:
            async with connection.transaction():
                # Revoke stale approvals first; only templates present in this complete
                # Meta snapshot are re-approved below.
                await connection.execute(
                    """UPDATE whatsapp_message_templates
                       SET status='pending', verified_at=NULL, updated_at=now()
                       WHERE workspace_id=$1 AND account_id=$2""",
                    workspace_id, account_id,
                )
                for item in templates:
                    provider_id = item.get("id")
                    name = item.get("name")
                    language = item.get("language")
                    provider_status = item.get("status")
                    category = str(item.get("category") or "").lower()
                    components = item.get("components") if isinstance(item.get("components"), list) else []
                    mapped_status = status_map.get(str(provider_status or "").upper())
                    if (
                        not isinstance(provider_id, (str, int))
                        or not str(provider_id).strip()
                        or not isinstance(name, str) or not name.strip()
                        or not isinstance(language, str) or not language.strip()
                        or category not in {"marketing", "utility", "authentication"}
                        or mapped_status is None
                    ):
                        skipped += 1
                        continue
                    await connection.execute(
                        """INSERT INTO whatsapp_message_templates
                           (workspace_id, account_id, template_name, language_code, category,
                            provider_template_id, status, provider_status, components, verified_at, updated_at)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,
                                   CASE WHEN $7='approved' THEN now() ELSE NULL END, now())
                           ON CONFLICT (account_id, template_name, language_code)
                           DO UPDATE SET
                             workspace_id=EXCLUDED.workspace_id,
                             category=EXCLUDED.category,
                             provider_template_id=EXCLUDED.provider_template_id,
                             status=EXCLUDED.status,
                             provider_status=EXCLUDED.provider_status,
                             components=EXCLUDED.components,
                             verified_at=CASE WHEN EXCLUDED.status='approved'
                                              THEN now() ELSE NULL END,
                             updated_at=now()""",
                        workspace_id, account_id, name.strip(), language.strip(),
                        category, str(provider_id).strip(), mapped_status,
                        str(provider_status).upper(), json.dumps(components),
                    )
                    synced += 1
    except Exception:
        raise HTTPException(status_code=503, detail="whatsapp_template_persistence_unavailable") from None

    return {
        "account_id": str(account_id),
        "templates_received": len(templates),
        "templates_synced": synced,
        "templates_skipped": skipped,
        "sending_enabled": False,
        "template_components_persisted": True,
    }
