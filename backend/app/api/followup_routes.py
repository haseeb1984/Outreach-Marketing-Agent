"""Workspace-authorized campaign follow-up sequences and scheduler endpoint."""
from __future__ import annotations
import hmac
import os
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.api.auth_routes import _authenticated, _check_csrf

router = APIRouter(prefix="/api/v1", tags=["campaign-followups"])

def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="database_not_configured")
    return pool

async def _authorize(request: Request, workspace_id: str, role: str, session: dict):
    store = getattr(request.app.state, "auth_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await store.authorize_workspace(user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role):
        raise HTTPException(status_code=404, detail="workspace_not_found")

class FollowupStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delay_minutes: int = Field(ge=0, le=43200)
    subject_template: str | None = Field(default=None, max_length=300)
    body_template: str = Field(min_length=1, max_length=10000)

class FollowupSequenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    channel: str
    steps: list[FollowupStep] = Field(min_length=1, max_length=10)
    @field_validator("channel")
    @classmethod
    def valid_channel(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"email", "whatsapp"}:
            raise ValueError("invalid_channel")
        return value

class SequenceStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    status: str

class FollowupDeliveryResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    delivery_id: UUID
    outcome: str
    reason: str = Field(min_length=12, max_length=2000)
    evidence_url: str = Field(min_length=9, max_length=2048)
    @field_validator("outcome")
    @classmethod
    def valid_outcome(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"delivered", "not_delivered"}:
            raise ValueError("invalid_resolution_outcome")
        return value
    @field_validator("evidence_url")
    @classmethod
    def valid_evidence_url(cls, value: str) -> str:
        if not value.strip().startswith("https://"):
            raise ValueError("https_evidence_url_required")
        return value.strip()

class FollowupEnroll(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    prospect_id: UUID

@router.post("/campaigns/{campaign_id}/follow-up-sequences", status_code=201)
async def create_followup_sequence(campaign_id: UUID, payload: FollowupSequenceCreate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    from app.services.followup_store import FollowupStore
    try:
        steps = [step.model_dump() for step in payload.steps]
        return await FollowupStore(_pool(request)).create_sequence(
            workspace_id=payload.workspace_id, campaign_id=campaign_id, actor_id=session["user_id"],
            name=payload.name, channel=payload.channel, steps=steps,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="followup_sequence_create_unavailable") from None

@router.get("/follow-up-sequences")
async def list_followup_sequences(request: Request, workspace_id: str = Query(min_length=1, max_length=200),
                                  campaign_id: UUID | None = None):
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    from app.services.followup_store import FollowupStore
    try:
        return {"items": await FollowupStore(_pool(request)).list_sequences(workspace_id=workspace_id, campaign_id=campaign_id)}
    except Exception:
        raise HTTPException(status_code=503, detail="followup_sequence_list_unavailable") from None

@router.patch("/follow-up-sequences/{sequence_id}")
async def update_followup_sequence(sequence_id: UUID, payload: SequenceStatusUpdate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    from app.services.followup_store import FollowupStore
    try:
        result = await FollowupStore(_pool(request)).set_sequence_status(
            workspace_id=payload.workspace_id, sequence_id=sequence_id, status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="followup_sequence_update_unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="followup_sequence_not_found")
    return result

@router.post("/follow-up-sequences/{sequence_id}/enroll", status_code=201)
async def enroll_followup(sequence_id: UUID, payload: FollowupEnroll, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    from app.services.followup_store import FollowupStore
    try:
        return await FollowupStore(_pool(request)).enroll(
            workspace_id=payload.workspace_id, sequence_id=sequence_id,
            prospect_id=payload.prospect_id, actor_id=session["user_id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="followup_enrollment_unavailable") from None

@router.get("/follow-up-sequences/{sequence_id}/enrollments")
async def list_followup_enrollments(sequence_id: UUID, request: Request,
                                    workspace_id: str = Query(min_length=1, max_length=200),
                                    limit: int = Query(default=100, ge=1, le=200),
                                    offset: int = Query(default=0, ge=0, le=100000)):
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    from app.services.followup_store import FollowupStore
    try:
        return {"items": await FollowupStore(_pool(request)).list_enrollments(
            workspace_id=workspace_id, sequence_id=sequence_id, limit=limit, offset=offset,
        ), "limit": limit, "offset": offset}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="followup_enrollment_list_unavailable") from None

@router.patch("/follow-up-enrollments/{enrollment_id}")
async def update_followup_enrollment(enrollment_id: UUID, payload: SequenceStatusUpdate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    from app.services.followup_store import FollowupStore
    try:
        result = await FollowupStore(_pool(request)).set_enrollment_status(
            workspace_id=payload.workspace_id, enrollment_id=enrollment_id, status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="followup_enrollment_update_unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="followup_enrollment_not_found_or_terminal")
    return result

@router.post("/follow-up-enrollments/{enrollment_id}/resolve-delivery")
async def resolve_followup_delivery(enrollment_id: UUID, payload: FollowupDeliveryResolution, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    from app.services.followup_store import FollowupStore
    try:
        result = await FollowupStore(_pool(request)).resolve_delivery(
            workspace_id=payload.workspace_id, enrollment_id=enrollment_id,
            delivery_id=payload.delivery_id, outcome=payload.outcome,
            actor_id=session["user_id"], reason=payload.reason, evidence_url=payload.evidence_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="followup_delivery_resolution_unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="recoverable_followup_delivery_not_found")
    return result

@router.post("/follow-up-sequences/process-due")
async def process_due_followups(request: Request, limit: int = Query(default=50, ge=1, le=100)):
    expected = (os.getenv("CRON_SECRET") or "").strip()
    supplied = request.headers.get("authorization", "")
    if len(expected.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="scheduler_secret_not_configured")
    if not hmac.compare_digest(supplied, "Bearer " + expected):
        raise HTTPException(status_code=401, detail="scheduler_unauthorized")
    from app.services.followup_store import FollowupStore
    try:
        return await FollowupStore(_pool(request)).process_due(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="followup_scheduler_unavailable") from None
