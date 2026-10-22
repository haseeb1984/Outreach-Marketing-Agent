"""Workspace-authorized provider configuration diagnostics.

SMTP settings are deployment-level environment settings today; no credential is
returned to the browser. The test endpoint performs TLS + authentication only and
never sends a message. WhatsApp sending remains disabled pending Meta onboarding.
"""
from __future__ import annotations

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

    whatsapp_fields = {
        "access_token": settings.meta_whatsapp_access_token,
        "app_secret": settings.meta_whatsapp_app_secret,
        "phone_number_id": settings.meta_whatsapp_phone_number_id,
        "waba_id": settings.meta_whatsapp_waba_id,
    }
    missing_whatsapp = [key for key, value in whatsapp_fields.items()
                        if not isinstance(value, str) or not value.strip()]

    return {
        "workspace_id": workspace_id,
        "email": {
            "configuration_complete": not missing_email,
            "missing_fields": missing_email,
            "note": "Deployment-level SMTP configuration; presence does not prove successful authentication or delivery.",
        },
        "whatsapp": {
            "configuration_complete": not missing_whatsapp,
            "missing_fields": missing_whatsapp,
            "reason": "Meta onboarding and workspace-specific provider authorization are not yet verified.",
            "live_send_enabled": False,
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
