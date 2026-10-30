"""Workspace-authorized provider configuration diagnostics.

Deployment-level SMTP is a fallback; workspace SMTP and WhatsApp accounts are managed separately.
No credential is returned to the browser. Provider configuration is not proof of delivery.
"""
from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException, Query, Request

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings
from app.services.email_delivery import (
    EmailDeliveryFailed,
    EmailDeliveryNotConfigured,
    SMTPEmailDelivery,
)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


async def _require_workspace_role(request: Request, session: dict, workspace_id: str, role: str):
    store = getattr(request.app.state, "auth_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    return await store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
    )


@router.get("/status")
async def integration_status(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
):
    """Return safe, non-secret provider readiness for a workspace member."""
    _, _, session = await _authenticated(request)
    if not await _require_workspace_role(request, session, workspace_id, "viewer"):
        raise HTTPException(status_code=404, detail="workspace_not_found")

    email_fields = {
        "host": settings.smtp_host,
        "username": settings.smtp_username,
        "password": settings.smtp_password,
        "from_email": settings.smtp_from_email,
    }
    missing_email = [key for key, value in email_fields.items()
                     if not isinstance(value, str) or not value.strip()]
    if settings.smtp_starttls is not True:
        missing_email.append("starttls_required")
    if isinstance(settings.smtp_port, bool) or not isinstance(settings.smtp_port, int) or settings.smtp_port != 587:
        missing_email.append("smtp_port_587_required")

    whatsapp_fields = {
        "app_secret": settings.meta_whatsapp_app_secret,
        "webhook_verify_token": settings.meta_whatsapp_webhook_verify_token,
        "graph_api_version": settings.meta_graph_api_version,
        "credential_encryption_key": settings.provider_credential_encryption_key,
    }
    missing_whatsapp = [key for key, value in whatsapp_fields.items()
                        if not isinstance(value, str) or not value.strip()]
    if len((settings.meta_whatsapp_app_secret or "").encode("utf-8")) < 32:
        missing_whatsapp.append("app_secret_minimum_32_bytes")
    if len((settings.meta_whatsapp_webhook_verify_token or "").encode("utf-8")) < 32:
        missing_whatsapp.append("webhook_verify_token_minimum_32_bytes")
    dispatch_gate_enabled = bool(settings.whatsapp_dispatch_enabled) and os.getenv(
        "WHATSAPP_DISPATCH_ENABLED", ""
    ).strip().lower() in {"1", "true"}
    active_whatsapp_accounts = 0
    pool = getattr(request.app.state, "db_pool", None)
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                active_whatsapp_accounts = int(await conn.fetchval(
                    "SELECT count(*) FROM workspace_whatsapp_accounts WHERE workspace_id=$1 AND status='active' AND encrypted_access_token IS NOT NULL",
                    workspace_id,
                ) or 0)
        except Exception:
            missing_whatsapp.append("workspace_account_status_unavailable")

    return {
        "workspace_id": workspace_id,
        "email": {
            "configuration_complete": not missing_email,
            "missing_fields": missing_email,
            "note": "Deployment-level fallback SMTP configuration; TLS on port 587 is required, and presence does not prove successful authentication or inbox delivery.",
        },
        "whatsapp": {
            "configuration_complete": not missing_whatsapp,
            "missing_fields": missing_whatsapp,
            "active_workspace_accounts": active_whatsapp_accounts,
            "dispatch_feature_enabled": dispatch_gate_enabled,
            "webhook_endpoint": "/api/v1/webhooks/meta/whatsapp",
            "inbound_processing_available": not missing_whatsapp,
            "live_send_enabled": dispatch_gate_enabled and active_whatsapp_accounts > 0 and not missing_whatsapp,
            "reason": "Workspace account verification and WABA webhook subscription are performed per account. Meta business review, phone registration, template approval and provider-side setup remain external requirements.",
        },
    }


@router.post("/smtp/test")
async def test_smtp_connection(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
):
    """Test SMTP TLS and authentication without sending any email."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    if not await _require_workspace_role(request, session, workspace_id, "admin"):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    if settings.environment.lower() not in {"staging", "production"}:
        raise HTTPException(status_code=403, detail="smtp_connection_test_unavailable")

    delivery = SMTPEmailDelivery()
    try:
        await delivery.test_connection()
    except EmailDeliveryNotConfigured:
        raise HTTPException(status_code=503, detail="smtp_configuration_incomplete") from None
    except EmailDeliveryFailed:
        raise HTTPException(status_code=502, detail="smtp_connection_test_failed") from None
    return {
        "workspace_id": workspace_id,
        "ok": True,
        "message": "SMTP TLS connection and authentication succeeded. No email was sent.",
    }
