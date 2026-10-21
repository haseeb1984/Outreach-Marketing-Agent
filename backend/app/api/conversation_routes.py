"""Signed webhook inbox for inbound replies plus workspace-authorized message history."""
from __future__ import annotations
import hashlib
import hmac
import json
from datetime import datetime,timezone
from uuid import UUID
from fastapi import APIRouter,Header,HTTPException,Query,Request
from pydantic import BaseModel,ConfigDict,Field,field_validator
from app.api.auth_routes import _authenticated
from app.core.config import settings

router=APIRouter(prefix="/api/v1",tags=["conversations"])
MAX_WEBHOOK_BYTES=64*1024

class InboundReply(BaseModel):
 model_config=ConfigDict(extra="forbid")
 event_type: str=Field(pattern=r"^message\.received$")
 event_id: str=Field(min_length=1,max_length=300)
 workspace_id: str=Field(min_length=1,max_length=200)
 prospect_id: UUID
 provider: str=Field(min_length=1,max_length=80,pattern=r"^[A-Za-z0-9._-]+$")
 provider_message_id: str=Field(min_length=1,max_length=500)
 in_reply_to_provider_message_id: str|None=Field(default=None,max_length=500)
 channel: str
 body: str=Field(min_length=1,max_length=10000)
 occurred_at: datetime

 @field_validator("channel")
 @classmethod
 def valid_channel(cls,v: str)->str:
  if v not in {"email","whatsapp"}: raise ValueError("invalid_channel")
  return v
 @field_validator("body")
 @classmethod
 def nonblank_body(cls,v: str)->str:
  if not v.strip(): raise ValueError("empty_body")
  return v
 @field_validator("occurred_at")
 @classmethod
 def timezone_required(cls,v: datetime)->datetime:
  if v.tzinfo is None or v.utcoffset() is None: raise ValueError("timezone_required")
  return v

async def _read_bounded_body(request: Request) -> bytes:
 content_length=request.headers.get("content-length")
 if content_length:
  try:
   declared_length=int(content_length)
  except ValueError:
   raise HTTPException(status_code=400,detail="invalid_content_length") from None
  if declared_length<0:
   raise HTTPException(status_code=400,detail="invalid_content_length")
  if declared_length>MAX_WEBHOOK_BYTES:
   raise HTTPException(status_code=413,detail="payload_too_large")
 chunks=[]
 total_bytes=0
 async for chunk in request.stream():
  total_bytes+=len(chunk)
  if total_bytes>MAX_WEBHOOK_BYTES:
   raise HTTPException(status_code=413,detail="payload_too_large")
  chunks.append(chunk)
 return b"".join(chunks)

def expected_signature(raw: bytes,secret: str)->str:
 return "sha256="+hmac.new(secret.encode("utf-8"),raw,hashlib.sha256).hexdigest()

@router.post("/webhooks/inbound-replies",status_code=202)
async def inbound_reply_webhook(request: Request,x_outreach_signature: str|None=Header(default=None,alias="X-Outreach-Signature")):
 secret=(settings.outreach_webhook_secret or "").strip()
 if len(secret.encode("utf-8"))<32:
  raise HTTPException(status_code=503,detail="webhook_not_configured")
 raw=await _read_bounded_body(request)
 if not x_outreach_signature or not hmac.compare_digest(expected_signature(raw,secret),x_outreach_signature):
  raise HTTPException(status_code=401,detail="invalid_webhook_signature")
 try: payload=InboundReply.model_validate(json.loads(raw))
 except (ValueError,TypeError):
  raise HTTPException(status_code=422,detail="invalid_webhook_payload") from None
 store=getattr(request.app.state,"conversation_store",None)
 if store is None: raise HTTPException(status_code=503,detail="conversation_service_not_configured")
 try:
  return await store.ingest_reply(workspace_id=payload.workspace_id,prospect_id=payload.prospect_id,
   provider=payload.provider,event_id=payload.event_id,message_id=payload.provider_message_id,
   in_reply_to=payload.in_reply_to_provider_message_id,channel=payload.channel,body=payload.body,
   occurred_at=payload.occurred_at.astimezone(timezone.utc))
 except LookupError: raise HTTPException(status_code=404,detail="prospect_not_found") from None
 except Exception: raise HTTPException(status_code=503,detail="reply_ingest_unavailable") from None

@router.get("/prospects/{prospect_id}/messages")
async def list_messages(prospect_id: UUID,request: Request,workspace_id: str=Query(min_length=1,max_length=200),
                        limit: int=Query(default=50,ge=1,le=100),offset: int=Query(default=0,ge=0,le=100000)):
 _,_,session=await _authenticated(request)
 auth=getattr(request.app.state,"auth_store",None)
 if auth is None: raise HTTPException(status_code=503,detail="authentication_not_configured")
 if not await auth.authorize_workspace(user_id=session["user_id"],workspace_id=workspace_id,minimum_role="viewer"):
  raise HTTPException(status_code=404,detail="workspace_not_found")
 store=getattr(request.app.state,"conversation_store",None)
 if store is None: raise HTTPException(status_code=503,detail="conversation_service_not_configured")
 return {"items":await store.list_messages(workspace_id=workspace_id,prospect_id=prospect_id,limit=limit,offset=offset),"limit":limit,"offset":offset}
