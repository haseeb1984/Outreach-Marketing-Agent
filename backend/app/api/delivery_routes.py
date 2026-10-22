"""Explicit admin-triggered send for approved email drafts."""
from __future__ import annotations
from uuid import UUID
import os
from fastapi import APIRouter,HTTPException,Query,Request
from pydantic import BaseModel,ConfigDict,Field
from app.api.auth_routes import _authenticated,_check_csrf
from app.services.email_delivery import EmailDeliveryFailed,EmailDeliveryNotConfigured,SMTPEmailDelivery
from app.services.smtp_account_store import CredentialDecryptionFailed, CredentialEncryptionNotConfigured, SMTPAccountStore
from app.core.config import settings
router=APIRouter(prefix="/api/v1",tags=["outbound-delivery"])

def whatsapp_configuration_status(configuration=settings)->dict:
 """Report Meta WhatsApp setup presence only; never return credential values."""
 required = {
  "META_WHATSAPP_ACCESS_TOKEN": configuration.meta_whatsapp_access_token,
  "META_WHATSAPP_APP_SECRET": configuration.meta_whatsapp_app_secret,
  "META_WHATSAPP_WEBHOOK_VERIFY_TOKEN": configuration.meta_whatsapp_webhook_verify_token,
  "META_WHATSAPP_PHONE_NUMBER_ID": configuration.meta_whatsapp_phone_number_id,
  "META_WHATSAPP_WABA_ID": configuration.meta_whatsapp_waba_id,
 }
 missing = sorted(name for name, value in required.items() if not isinstance(value, str) or not value.strip())
 return {
  "configuration_complete": not missing,
  "missing_fields": missing,
  "coexistence_onboarding_required": True,
  "webhook_signature_verification_implemented": True,
  "inbound_event_persistence_implemented": True,
  "live_send_enabled": False,
 }

def _store(r: Request):
 s=getattr(r.app.state,"delivery_store",None)
 if s is None: raise HTTPException(status_code=503,detail="delivery_service_not_configured")
 return s
async def _authorize(r: Request,w: str,role: str,session: dict):
 a=getattr(r.app.state,"auth_store",None)
 if a is None: raise HTTPException(status_code=503,detail="authentication_not_configured")
 if not await a.authorize_workspace(user_id=session["user_id"],workspace_id=w,minimum_role=role): raise HTTPException(status_code=404,detail="workspace_not_found")
class EnqueueDelivery(BaseModel):
 model_config=ConfigDict(extra="forbid")
 workspace_id: str=Field(min_length=1,max_length=200)
 idempotency_key: str=Field(min_length=8,max_length=200,pattern=r"^[A-Za-z0-9._:-]+$")
 email_account_id: UUID|None=None
@router.post("/drafts/{draft_id}/enqueue",status_code=201)
async def enqueue_delivery(draft_id: UUID,payload: EnqueueDelivery,request: Request):
 _,_,s=await _authenticated(request); _check_csrf(request,s); await _authorize(request,payload.workspace_id,"admin",s)
 try: return await _store(request).enqueue(workspace_id=payload.workspace_id,draft_id=draft_id,actor_id=s["user_id"],idempotency_key=payload.idempotency_key,email_account_id=payload.email_account_id)
 except LookupError as exc: raise HTTPException(status_code=404,detail=str(exc)) from None
 except ValueError as e: raise HTTPException(status_code=409 if str(e)=="idempotency_key_conflict" else 422,detail=str(e)) from None
 except Exception: raise HTTPException(status_code=503,detail="delivery_enqueue_unavailable") from None
@router.get("/deliveries")
async def list_deliveries(request: Request,workspace_id: str=Query(min_length=1,max_length=200),limit: int=Query(default=50,ge=1,le=100),offset: int=Query(default=0,ge=0,le=100000)):
 _,_,s=await _authenticated(request); await _authorize(request,workspace_id,"viewer",s)
 return {"items":await _store(request).list_deliveries(workspace_id=workspace_id,limit=limit,offset=offset),"limit":limit,"offset":offset}
@router.post("/deliveries/{delivery_id}/send")
async def send_delivery(delivery_id: UUID, payload: EnqueueDelivery, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    store = _store(request)
    subscriptions = getattr(request.app.state, "subscription_store", None)
    if subscriptions is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")

    # One stable reservation per queued delivery prevents a caller from bypassing
    # the quota by changing the request idempotency key on a retry.
    reservation_key = f"delivery-send:{delivery_id}"
    try:
        reservation = await subscriptions.reserve_usage(
            workspace_id=payload.workspace_id,
            feature="email_sends",
            idempotency_key=reservation_key,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    if not reservation.get("allowed"):
        reason = reservation.get("reason", "entitlement_denied")
        status_code = 429 if reason == "quota_exhausted" else 403
        raise HTTPException(status_code=status_code, detail=reason)
    # A reservation replay may belong to a concurrent or interrupted send. Never let
    # a second request claim/send it or release quota reserved by the first request.
    if reservation.get("reason") == "idempotent_replay" or reservation.get("status") == "consumed":
        raise HTTPException(status_code=409, detail="delivery_send_key_already_used")

    reservation_id = reservation["reservation_id"]
    try:
        data = await store.claim(workspace_id=payload.workspace_id, delivery_id=delivery_id)
    except LookupError:
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=404, detail="delivery_not_found") from None
    except ValueError as exc:
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception:
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=503, detail="delivery_claim_unavailable") from None

    try:
        if data.get("email_account_id"):
            pool = getattr(request.app.state, "db_pool", None)
            if pool is None:
                raise EmailDeliveryNotConfigured("email_account_service_not_configured")
            configuration = await SMTPAccountStore(pool).get_config(
                workspace_id=payload.workspace_id,
                account_id=UUID(data["email_account_id"]),
            )
            await SMTPEmailDelivery(configuration).send_outreach_email(
                recipient=data["recipient"], subject=data["subject"], body=data["body"]
            )
        else:
            await SMTPEmailDelivery().send_outreach_email(
                recipient=data["recipient"], subject=data["subject"], body=data["body"]
            )
    except LookupError:
        await store.finish(workspace_id=payload.workspace_id, delivery_id=delivery_id,
                           error_code="email_account_not_available")
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=409, detail="email_account_not_available") from None
    except CredentialEncryptionNotConfigured:
        await store.finish(workspace_id=payload.workspace_id, delivery_id=delivery_id,
                           error_code="provider_encryption_not_configured")
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=503, detail="provider_credential_encryption_not_configured") from None
    except CredentialDecryptionFailed:
        await store.finish(workspace_id=payload.workspace_id, delivery_id=delivery_id,
                           error_code="provider_credential_decryption_failed")
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=503, detail="provider_credential_decryption_failed") from None
    except EmailDeliveryNotConfigured:
        await store.finish(workspace_id=payload.workspace_id, delivery_id=delivery_id,
                           error_code="provider_not_configured")
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=503, detail="email_provider_not_configured") from None
    except ValueError:
        # Validation errors occur before SMTP is called and are safe to release.
        await store.finish(workspace_id=payload.workspace_id, delivery_id=delivery_id,
                           error_code="invalid_message")
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
        )
        raise HTTPException(status_code=422, detail="email_message_invalid") from None
    except EmailDeliveryFailed:
        # The remote server may have accepted the message before the connection
        # failed. Keep the quota consumed and do not make the send retryable.
        await store.finish(workspace_id=payload.workspace_id, delivery_id=delivery_id,
                           error_code="delivery_outcome_unknown")
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
        )
        raise HTTPException(status_code=502, detail="delivery_outcome_unknown") from None
    except Exception:
        await store.finish(workspace_id=payload.workspace_id, delivery_id=delivery_id,
                           error_code="delivery_outcome_unknown")
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
        )
        raise HTTPException(status_code=502, detail="delivery_outcome_unknown") from None

    if not await store.finish(workspace_id=payload.workspace_id, delivery_id=delivery_id):
        # SMTP accepted the message; do not release the quota on a persistence issue.
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
        )
        raise HTTPException(status_code=503, detail="delivery_status_persistence_failed")
    if not await subscriptions.finish_reservation(
        workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
    ):
        raise HTTPException(status_code=503, detail="delivery_quota_persistence_failed")
    return {"id": str(delivery_id), "status": "sent"}



def smtp_configuration_status(configuration=settings)->dict:
 """Return safe SMTP configuration diagnostics without exposing values or testing credentials."""
 required = {
  "SMTP_HOST": configuration.smtp_host,
  "SMTP_USERNAME": configuration.smtp_username,
  "SMTP_PASSWORD": configuration.smtp_password,
  "SMTP_FROM_EMAIL": configuration.smtp_from_email,
 }
 missing = sorted(name for name, value in required.items() if not isinstance(value, str) or not value.strip())
 port = configuration.smtp_port
 port_valid = isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535
 tls_enabled = configuration.smtp_starttls is True
 if not port_valid:
  missing.append("SMTP_PORT")
 if not tls_enabled:
  missing.append("SMTP_STARTTLS")
 return {
  "configuration_complete": not missing,
  "missing_fields": sorted(set(missing)),
  "port_valid": port_valid,
  "starttls_enabled": tls_enabled,
  "connection_tested": False,
 }


@router.post("/integrations/smtp/test")
async def test_smtp_connection(request: Request, workspace_id: str = Query(min_length=1, max_length=200)):
 """Explicit workspace-admin staging test; authenticates SMTP but never sends email."""
 _, _, session = await _authenticated(request)
 _check_csrf(request, session)
 await _authorize(request, workspace_id, "admin", session)
 runtime_environment = settings.environment.strip().lower()
 platform_environment = os.getenv("VERCEL_ENV", "").strip().lower()
 if runtime_environment not in {"staging", "production"} and platform_environment not in {"preview", "production"}:
  raise HTTPException(status_code=404, detail="smtp_connection_test_unavailable")
 try:
  await SMTPEmailDelivery().test_connection()
 except EmailDeliveryNotConfigured:
  raise HTTPException(status_code=422, detail="smtp_configuration_incomplete") from None
 except EmailDeliveryFailed:
  raise HTTPException(status_code=502, detail="smtp_connection_test_failed") from None
 return {"status": "authenticated", "email_sent": False,
         "message": "SMTP TLS connection and authentication succeeded; no email was sent."}


@router.get("/integrations/status")
async def integrations_status(request: Request, workspace_id: str=Query(min_length=1,max_length=200)):
 """Workspace-scoped integration readiness without returning any credential material."""
 _,_,session=await _authenticated(request)
 await _authorize(request,workspace_id,"viewer",session)
 smtp=smtp_configuration_status()
 return {
  "workspace_id": workspace_id,
  "email": {
   "provider": "smtp",
   **smtp,
   "note": "Configuration presence is not proof that SMTP authentication or delivery works.",
  },
  "whatsapp": {
   "provider": "meta_whatsapp_cloud_api",
   **whatsapp_configuration_status(),
   "reason": "official_webhook_and_send_adapter_not_implemented",
  },
 }
