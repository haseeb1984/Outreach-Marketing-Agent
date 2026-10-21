"""Authenticated, workspace-authorized prospect CRM endpoints."""
from __future__ import annotations

from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.services.prospect_store import ProspectStore

router = APIRouter(prefix="/api/v1/prospects", tags=["prospects"])
ALLOWED_STAGES = {"new", "qualified", "approved", "contacted", "replied", "converted", "disqualified", "do_not_contact"}


def _store(request: Request) -> ProspectStore:
    store = getattr(request.app.state, "prospect_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="prospect_service_not_configured")
    return store


async def _authorize(request: Request, workspace_id: str, minimum_role: str = "viewer"):
    auth_store, _, session = await _authenticated(request)
    allowed = await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role=minimum_role,
    )
    if not allowed:
        # Do not disclose whether another workspace exists.
        raise HTTPException(status_code=404, detail="workspace_not_found")
    return session


def _https_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("url_must_be_https")
    return value.strip()


class ProspectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=240)
    role: str | None = Field(default=None, max_length=160)
    contact_email: str | None = Field(default=None, max_length=320)
    website_url: str = Field(min_length=8, max_length=2048)
    evidence_url: str = Field(min_length=8, max_length=2048)
    fit_reason: str = Field(min_length=1, max_length=2000)
    verified_facts: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("website_url", "evidence_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        return _https_url(value)

    @field_validator("verified_facts")
    @classmethod
    def facts_are_bounded(cls, value: list[str]) -> list[str]:
        if any(not isinstance(item, str) or not item.strip() or len(item) > 1000 for item in value):
            raise ValueError("verified_facts_must_be_nonempty_bounded_strings")
        return list(dict.fromkeys(item.strip() for item in value))


class ProspectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    stage: str | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_STAGES:
            raise ValueError("invalid_prospect_stage")
        return value


@router.get("")
async def list_prospects(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    stage: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
):
    if stage is not None and stage not in ALLOWED_STAGES:
        raise HTTPException(status_code=422, detail="invalid_prospect_stage")
    await _authorize(request, workspace_id, "viewer")
    return {"items": await _store(request).list_prospects(
        workspace_id=workspace_id, stage=stage, limit=limit, offset=offset,
    ), "limit": limit, "offset": offset}


@router.post("", status_code=201)
async def create_prospect(payload: ProspectCreate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member")
    try:
        prospect = await _store(request).create_prospect(
            workspace_id=payload.workspace_id, created_by=session["user_id"],
            name=payload.name, company=payload.company, role=payload.role,
            contact_email=payload.contact_email, website_url=payload.website_url,
            evidence_url=payload.evidence_url, fit_reason=payload.fit_reason,
            verified_facts=payload.verified_facts,
        )
    except Exception as exc:
        # Do not return database details or SQL to the caller.
        if type(exc).__name__ == "UniqueViolationError":
            raise HTTPException(status_code=409, detail="prospect_evidence_already_exists") from None
        raise HTTPException(status_code=503, detail="prospect_save_unavailable") from None
    return prospect


@router.patch("/{prospect_id}")
async def update_prospect(prospect_id: UUID, payload: ProspectUpdate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member")
    try:
        result = await _store(request).update_prospect(
            workspace_id=payload.workspace_id, prospect_id=prospect_id,
            stage=payload.stage, notes=payload.notes,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="no_prospect_updates_supplied") from None
    except Exception:
        raise HTTPException(status_code=503, detail="prospect_update_unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="prospect_not_found")
    return result


@router.delete("/{prospect_id}", status_code=204)
async def archive_prospect(prospect_id: UUID, request: Request, workspace_id: str = Query(min_length=1, max_length=200)):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin")
    try:
        archived = await _store(request).archive_prospect(workspace_id=workspace_id, prospect_id=prospect_id)
    except Exception:
        raise HTTPException(status_code=503, detail="prospect_archive_unavailable") from None
    if not archived:
        raise HTTPException(status_code=404, detail="prospect_not_found")
