"""Explicit admin-triggered send for approved email drafts."""
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter,HTTPException,Query,Request
from pydantic import BaseModel,ConfigDict,Field
from app.api.auth_routes import _authenticated,_check_csrf
from app.services.email_delivery import EmailDeliveryFailed,EmailDeliveryNotConfigured,SMTPEmailDelivery
router=APIRouter(prefix="/api/v1",tags=["outbound-delivery"])
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
@router.post("/drafts/{draft_id}/enqueue",status_code=201)
async def enqueue_delivery(draft_id: UUID,payload: EnqueueDelivery,request: Request):
 _,_,s=await _authenticated(request); _check_csrf(request,s); await _authorize(request,payload.workspace_id,"admin",s)
 try: return await _store(request).enqueue(workspace_id=payload.workspace_id,draft_id=draft_id,actor_id=s["user_id"],idempotency_key=payload.idempotency_key)
 except LookupError: raise HTTPException(status_code=404,detail="draft_not_found") from None
 except ValueError as e: raise HTTPException(status_code=409 if str(e)=="idempotency_key_conflict" else 422,detail=str(e)) from None
 except Exception: raise HTTPException(status_code=503,detail="delivery_enqueue_unavailable") from None
@router.get("/deliveries")
async def list_deliveries(request: Request,workspace_id: str=Query(min_length=1,max_length=200),limit: int=Query(default=50,ge=1,le=100),offset: int=Query(default=0,ge=0,le=100000)):
 _,_,s=await _authenticated(request); await _authorize(request,workspace_id,"viewer",s)
 return {"items":await _store(request).list_deliveries(workspace_id=workspace_id,limit=limit,offset=offset),"limit":limit,"offset":offset}
@router.post("/deliveries/{delivery_id}/send")
async def send_delivery(delivery_id: UUID,payload: EnqueueDelivery,request: Request):
 _,_,s=await _authenticated(request); _check_csrf(request,s); await _authorize(request,payload.workspace_id,"admin",s); store=_store(request)
 try: data=await store.claim(workspace_id=payload.workspace_id,delivery_id=delivery_id)
 except LookupError: raise HTTPException(status_code=404,detail="delivery_not_found") from None
 except ValueError as e: raise HTTPException(status_code=409,detail=str(e)) from None
 try: await SMTPEmailDelivery().send_outreach_email(recipient=data["recipient"],subject=data["subject"],body=data["body"])
 except EmailDeliveryNotConfigured:
  await store.finish(workspace_id=payload.workspace_id,delivery_id=delivery_id,error_code="provider_not_configured")
  raise HTTPException(status_code=503,detail="email_provider_not_configured") from None
 except (EmailDeliveryFailed,ValueError):
  await store.finish(workspace_id=payload.workspace_id,delivery_id=delivery_id,error_code="provider_delivery_failed")
  raise HTTPException(status_code=502,detail="email_provider_delivery_failed") from None
 except Exception:
  await store.finish(workspace_id=payload.workspace_id,delivery_id=delivery_id,error_code="provider_delivery_failed")
  raise HTTPException(status_code=502,detail="email_provider_delivery_failed") from None
 if not await store.finish(workspace_id=payload.workspace_id,delivery_id=delivery_id): raise HTTPException(status_code=503,detail="delivery_status_persistence_failed")
 return {"id":str(delivery_id),"status":"sent"}
