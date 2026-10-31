"""Explicit admin-triggered send for approved email drafts."""
from __future__ import annotations
from uuid import UUID
from datetime import datetime
import os
import hmac
from fastapi import APIRouter,HTTPException,Query,Request
from pydantic import BaseModel,ConfigDict,Field
from app.api.auth_routes import _authenticated,_check_csrf
from app.services.email_delivery import EmailDeliveryFailed,EmailDeliveryNotConfigured,SMTPEmailDelivery
from app.services.smtp_account_store import CredentialDecryptionFailed, CredentialEncryptionNotConfigured, SMTPAccountStore
from app.services.email_provider_event_store import EmailProviderEventStore
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

async def _settle_delivery_attempt(
    store, subscriptions, *, workspace_id: str, delivery_id: UUID,
    reservation_id: str, error_code: str | None, quota_outcome: str,
) -> tuple[bool, bool]:
    """Persist delivery and quota outcomes independently so one failure cannot skip the other."""
    try:
        delivery_saved = await store.finish(
            workspace_id=workspace_id, delivery_id=delivery_id, error_code=error_code
        )
    except Exception:
        delivery_saved = False
    try:
        quota_saved = await subscriptions.finish_reservation(
            workspace_id=workspace_id, reservation_id=reservation_id, outcome=quota_outcome
        )
    except Exception:
        quota_saved = False
    return delivery_saved, quota_saved
class EnqueueDelivery(BaseModel):
 model_config=ConfigDict(extra="forbid")
 workspace_id: str=Field(min_length=1,max_length=200)
 idempotency_key: str=Field(min_length=8,max_length=200,pattern=r"^[A-Za-z0-9._:-]+$")
 email_account_id: UUID|None=None
 scheduled_at: datetime|None=None
@router.post("/drafts/{draft_id}/enqueue",status_code=201)
async def enqueue_delivery(draft_id: UUID,payload: EnqueueDelivery,request: Request):
 _,_,s=await _authenticated(request); _check_csrf(request,s); await _authorize(request,payload.workspace_id,"admin",s)
 try: return await _store(request).enqueue(workspace_id=payload.workspace_id,draft_id=draft_id,actor_id=s["user_id"],idempotency_key=payload.idempotency_key,email_account_id=payload.email_account_id,scheduled_at=payload.scheduled_at)
 except LookupError as exc: raise HTTPException(status_code=404,detail=str(exc)) from None
 except ValueError as e: raise HTTPException(status_code=409 if str(e) in {"idempotency_key_conflict", "campaign_archived", "campaign_paused", "contact_replied", "delivery_schedule_conflict"} else 422,detail=str(e)) from None
 except Exception: raise HTTPException(status_code=503,detail="delivery_enqueue_unavailable") from None
@router.post("/deliveries/process-due")
async def process_due_deliveries(request: Request, limit: int = Query(default=25, ge=1, le=100)):
    """Cron entry point for approved, due deliveries; protected by a dedicated secret."""
    expected = os.getenv("CRON_SECRET", "").strip()
    supplied = request.headers.get("authorization", "")
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="scheduler_secret_not_configured")
    if not hmac.compare_digest(supplied, "Bearer " + expected):
        raise HTTPException(status_code=401, detail="scheduler_unauthorized")
    store = _store(request)
    subscriptions = getattr(request.app.state, "subscription_store", None)
    if subscriptions is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    try:
        due = await store.list_due(limit=limit)
    except Exception:
        raise HTTPException(status_code=503, detail="due_delivery_lookup_unavailable") from None
    results = []
    for item in due:
        workspace_id = item["workspace_id"]
        delivery_id = UUID(item["delivery_id"])
        reservation = None
        data = None
        try:
            reservation = await subscriptions.reserve_usage(
                workspace_id=workspace_id, feature="email_sends",
                idempotency_key=f"delivery-send:{delivery_id}",
            )
            reservation_replayed = reservation.get("reason") == "idempotent_replay"
            if (
                not reservation.get("allowed")
                or reservation.get("status") == "consumed"
                or (reservation_replayed and reservation.get("status") != "reserved")
            ):
                results.append({"delivery_id": str(delivery_id), "status": "skipped", "reason": reservation.get("reason", "quota_denied")})
                continue
            data = await store.claim(workspace_id=workspace_id, delivery_id=delivery_id)
            if data.get("email_account_id"):
                pool = getattr(request.app.state, "db_pool", None)
                if pool is None:
                    raise EmailDeliveryNotConfigured("email_account_service_not_configured")
                configuration = await SMTPAccountStore(pool).get_config(
                    workspace_id=workspace_id, account_id=UUID(data["email_account_id"])
                )
                sender = SMTPEmailDelivery(configuration)
            else:
                sender = SMTPEmailDelivery()
            await sender.send_outreach_email(
                recipient=data["recipient"], subject=data["subject"], body=data["body"],
                delivery_id=data["delivery_id"], workspace_id=data["workspace_id"],
                prospect_id=data["prospect_id"],
            )
            delivery_saved, quota_saved = await _settle_delivery_attempt(
                store, subscriptions, workspace_id=workspace_id, delivery_id=delivery_id,
                reservation_id=reservation["reservation_id"], error_code=None, quota_outcome="consumed",
            )
            results.append({"delivery_id": str(delivery_id), "status": "sent" if delivery_saved and quota_saved else "settlement_pending"})
        except ValueError as exc:
            # If this was a replay, another scheduler may own the live attempt.
            # Never release its reservation when our competing claim loses.
            if reservation and reservation.get("reservation_id") and not (
                reservation.get("reason") == "idempotent_replay" and data is None
            ):
                await _settle_delivery_attempt(
                    store, subscriptions, workspace_id=workspace_id, delivery_id=delivery_id,
                    reservation_id=reservation["reservation_id"], error_code=str(exc)[:100], quota_outcome="released",
                )
            results.append({"delivery_id": str(delivery_id), "status": "blocked", "reason": str(exc)[:100]})
        except (EmailDeliveryNotConfigured, CredentialEncryptionNotConfigured, CredentialDecryptionFailed, LookupError):
            if reservation and reservation.get("reservation_id") and not (
                reservation.get("reason") == "idempotent_replay" and data is None
            ):
                await _settle_delivery_attempt(
                    store, subscriptions, workspace_id=workspace_id, delivery_id=delivery_id,
                    reservation_id=reservation["reservation_id"], error_code="provider_not_configured",
                    quota_outcome="released",
                )
            results.append({"delivery_id": str(delivery_id), "status": "failed", "reason": "provider_not_configured"})
        except EmailDeliveryFailed:
            if reservation and reservation.get("reservation_id") and data is not None:
                await _settle_delivery_attempt(
                    store, subscriptions, workspace_id=workspace_id, delivery_id=delivery_id,
                    reservation_id=reservation["reservation_id"], error_code="delivery_outcome_unknown", quota_outcome="consumed",
                )
            results.append({"delivery_id": str(delivery_id), "status": "uncertain"})
        except Exception:
            # A claimed send may have reached SMTP; never make an ambiguous attempt retryable.
            if reservation and reservation.get("reservation_id") and data is not None:
                await _settle_delivery_attempt(
                    store, subscriptions, workspace_id=workspace_id, delivery_id=delivery_id,
                    reservation_id=reservation["reservation_id"], error_code="delivery_outcome_unknown", quota_outcome="consumed",
                )
            results.append({"delivery_id": str(delivery_id), "status": "uncertain"})
    return {"processed": len(results), "items": results}


@router.post("/deliveries/reconcile-stale")
async def reconcile_stale_deliveries(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    older_than_seconds: int = Query(default=900, ge=60, le=86400),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Admin-triggered, bounded recovery; ambiguous sends are never automatically retried."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin", session)
    try:
        reconciled = await _store(request).reconcile_stale_processing(
            workspace_id=workspace_id,
            older_than_seconds=older_than_seconds,
            limit=limit,
        )
        return {
            "workspace_id": workspace_id,
            "reconciled_count": reconciled,
            "status": "uncertain",
            "automatic_retry": False,
            "note": "Review provider records before manually resolving any ambiguous send.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="delivery_reconciliation_unavailable") from None


class DeliveryScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    scheduled_at: datetime


@router.patch("/deliveries/{delivery_id}/schedule")
async def reschedule_delivery(delivery_id: UUID, payload: DeliveryScheduleUpdate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    try:
        result = await _store(request).reschedule(
            workspace_id=payload.workspace_id, delivery_id=delivery_id,
            scheduled_at=payload.scheduled_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="delivery_reschedule_unavailable") from None
    if result is None:
        raise HTTPException(status_code=409, detail="delivery_not_queued_or_not_found")
    return result


@router.delete("/deliveries/{delivery_id}")
async def cancel_delivery(
    delivery_id: UUID, request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin", session)
    try:
        cancelled = await _store(request).cancel(workspace_id=workspace_id, delivery_id=delivery_id)
    except Exception:
        raise HTTPException(status_code=503, detail="delivery_cancel_unavailable") from None
    if not cancelled:
        raise HTTPException(status_code=409, detail="delivery_not_queued_or_not_found")
    return {"id": str(delivery_id), "status": "cancelled"}


@router.get("/deliveries")
async def list_deliveries(request: Request,workspace_id: str=Query(min_length=1,max_length=200),limit: int=Query(default=50,ge=1,le=100),offset: int=Query(default=0,ge=0,le=100000)):
 _,_,s=await _authenticated(request); await _authorize(request,workspace_id,"viewer",s)
 return {"items":await _store(request).list_deliveries(workspace_id=workspace_id,limit=limit,offset=offset),"limit":limit,"offset":offset}
@router.get("/deliveries/{delivery_id}/provider-events")
async def list_email_provider_events(
    delivery_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
):
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="email_event_store_not_configured")
    try:
        items = await EmailProviderEventStore(pool).list_events(
            workspace_id=workspace_id, delivery_id=delivery_id, limit=limit,
        )
        return {"items": items, "limit": limit}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="email_provider_event_history_unavailable") from None


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
    # A consumed reservation is terminal. A still-reserved replay may be a
    # crash-before-claim recovery; the queue's atomic claim decides which request
    # owns the attempt. Losing replay requests must never release the winner's quota.
    reservation_replayed = reservation.get("reason") == "idempotent_replay"
    if reservation.get("status") == "consumed" or (
        reservation_replayed and reservation.get("status") != "reserved"
    ):
        raise HTTPException(status_code=409, detail="delivery_send_key_already_used")

    reservation_id = reservation["reservation_id"]
    try:
        data = await store.claim(workspace_id=payload.workspace_id, delivery_id=delivery_id)
    except LookupError:
        if not reservation_replayed:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
            )
        raise HTTPException(status_code=404, detail="delivery_not_found") from None
    except ValueError as exc:
        if not reservation_replayed:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
            )
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception:
        if not reservation_replayed:
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
                recipient=data["recipient"], subject=data["subject"], body=data["body"],
                delivery_id=data["delivery_id"], workspace_id=data["workspace_id"],
                prospect_id=data["prospect_id"],
            )
        else:
            await SMTPEmailDelivery().send_outreach_email(
                recipient=data["recipient"], subject=data["subject"], body=data["body"],
                delivery_id=data["delivery_id"], workspace_id=data["workspace_id"],
                prospect_id=data["prospect_id"],
            )
    except LookupError:
        await _settle_delivery_attempt(
            store, subscriptions, workspace_id=payload.workspace_id, delivery_id=delivery_id,
            reservation_id=reservation_id, error_code="email_account_not_available", quota_outcome="released",
        )
        raise HTTPException(status_code=409, detail="email_account_not_available") from None
    except CredentialEncryptionNotConfigured:
        await _settle_delivery_attempt(
            store, subscriptions, workspace_id=payload.workspace_id, delivery_id=delivery_id,
            reservation_id=reservation_id, error_code="provider_encryption_not_configured", quota_outcome="released",
        )
        raise HTTPException(status_code=503, detail="provider_credential_encryption_not_configured") from None
    except CredentialDecryptionFailed:
        await _settle_delivery_attempt(
            store, subscriptions, workspace_id=payload.workspace_id, delivery_id=delivery_id,
            reservation_id=reservation_id, error_code="provider_credential_decryption_failed", quota_outcome="released",
        )
        raise HTTPException(status_code=503, detail="provider_credential_decryption_failed") from None
    except EmailDeliveryNotConfigured:
        await _settle_delivery_attempt(
            store, subscriptions, workspace_id=payload.workspace_id, delivery_id=delivery_id,
            reservation_id=reservation_id, error_code="provider_not_configured", quota_outcome="released",
        )
        raise HTTPException(status_code=503, detail="email_provider_not_configured") from None
    except ValueError:
        # Validation errors occur before SMTP is called and are safe to release.
        await _settle_delivery_attempt(
            store, subscriptions, workspace_id=payload.workspace_id, delivery_id=delivery_id,
            reservation_id=reservation_id, error_code="invalid_message", quota_outcome="released",
        )
        raise HTTPException(status_code=422, detail="email_message_invalid") from None
    except EmailDeliveryFailed:
        # The remote server may have accepted the message before the connection
        # failed. Keep the quota consumed and do not make the send retryable.
        await _settle_delivery_attempt(
            store, subscriptions, workspace_id=payload.workspace_id, delivery_id=delivery_id,
            reservation_id=reservation_id, error_code="delivery_outcome_unknown", quota_outcome="consumed",
        )
        raise HTTPException(status_code=502, detail="delivery_outcome_unknown") from None
    except Exception:
        await store.finish(workspace_id=payload.workspace_id, delivery_id=delivery_id,
                           error_code="delivery_outcome_unknown")
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
        )
        raise HTTPException(status_code=502, detail="delivery_outcome_unknown") from None

    delivery_saved, quota_saved = await _settle_delivery_attempt(
        store, subscriptions, workspace_id=payload.workspace_id, delivery_id=delivery_id,
        reservation_id=reservation_id, error_code=None, quota_outcome="consumed",
    )
    if not delivery_saved:
        # SMTP accepted the message; quota is still finalized even when status persistence fails.
        raise HTTPException(status_code=503, detail="delivery_status_persistence_failed")
    if not quota_saved:
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
 port_valid = isinstance(port, int) and not isinstance(port, bool) and port == 587
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
   "provider_feedback_webhook_configured": bool(settings.outreach_webhook_secret and len(settings.outreach_webhook_secret.strip().encode("utf-8")) >= 32),
   "provider_feedback_events": ["delivered", "deferred", "bounced", "complained", "unsubscribed"],
   "signed_one_click_unsubscribe": bool(settings.outreach_webhook_secret and len(settings.outreach_webhook_secret.strip().encode("utf-8")) >= 32 and settings.public_base_url and settings.public_base_url.strip().lower().startswith("https://")),
   "inbound_reply_webhook_implemented": True,
   "inbound_reply_webhook_configured": bool(settings.outreach_webhook_secret and len(settings.outreach_webhook_secret.strip().encode("utf-8")) >= 32),
   "provider_native_signature_verification_required_in_relay": True,
   "scheduled_campaign_dispatch_secret_configured": bool(os.getenv("CRON_SECRET", "").strip() and len(os.getenv("CRON_SECRET", "").strip().encode("utf-8")) >= 32),
   "scheduled_campaign_dispatch_endpoint": "/api/v1/deliveries/process-due",
  },
  "whatsapp": {
   "provider": "meta_whatsapp_cloud_api",
   **whatsapp_configuration_status(),
   "reason": "whatsapp_outbound_queue_implemented_dispatch_disabled_until_verified_worker",
   "outbound_queue_api_implemented": True,
  },
  "ai_outreach": {
   "provider": "openai_compatible_chat_completions",
   "configured": bool(settings.ai_api_key and settings.ai_api_key.strip()),
   "model": settings.ai_model if settings.ai_api_key else None,
   "generation_mode": "provider_ai" if settings.ai_api_key else "evidence_grounded_template_fallback",
   "human_approval_required": True,
   "automatic_send": False,
  },
 }
