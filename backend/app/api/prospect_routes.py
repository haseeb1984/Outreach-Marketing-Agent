"""Authenticated, workspace-authorized prospect CRM endpoints."""
from __future__ import annotations

import csv
import io
import re
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
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


async def _authorize(request: Request, workspace_id: str, minimum_role: str = "viewer", session: dict | None = None):
    if session is None:
        auth_store, _, session = await _authenticated(request)
    else:
        auth_store = getattr(request.app.state, "auth_store", None)
        if auth_store is None:
            raise HTTPException(status_code=503, detail="authentication_not_configured")
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
    contact_phone_e164: str | None = Field(default=None, min_length=9, max_length=16, pattern=r"^\+[1-9][0-9]{7,14}$")
    website_url: str = Field(min_length=8, max_length=2048)
    evidence_url: str = Field(min_length=8, max_length=2048)
    fit_reason: str = Field(min_length=1, max_length=2000)
    verified_facts: list[str] = Field(default_factory=list, max_length=30)
    project_id: UUID | None = None

    @field_validator("contact_email")
    @classmethod
    def validate_contact_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", cleaned):
            raise ValueError("invalid_contact_email")
        return cleaned or None

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


class ContactControlsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    email_suppressed: bool | None = None
    whatsapp_opt_in_confirmed: bool = False
    whatsapp_account_id: UUID | None = None
    whatsapp_opt_in_evidence_url: str | None = Field(default=None, max_length=2048)

    @field_validator("whatsapp_opt_in_evidence_url")
    @classmethod
    def validate_opt_in_evidence(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return _https_url(value)


class ProspectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    stage: str | None = None
    notes: str | None = Field(default=None, max_length=5000)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    company: str | None = Field(default=None, min_length=1, max_length=240)
    role: str | None = Field(default=None, max_length=160)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone_e164: str | None = Field(default=None, min_length=9, max_length=16, pattern=r"^\+[1-9][0-9]{7,14}$")
    website_url: str | None = Field(default=None, min_length=8, max_length=2048)
    evidence_url: str | None = Field(default=None, min_length=8, max_length=2048)
    fit_reason: str | None = Field(default=None, min_length=1, max_length=2000)
    project_id: UUID | None = None

    @field_validator("contact_email")
    @classmethod
    def validate_update_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", cleaned):
            raise ValueError("invalid_contact_email")
        return cleaned or None

    @field_validator("website_url", "evidence_url")
    @classmethod
    def validate_update_urls(cls, value: str | None) -> str | None:
        return _https_url(value) if value is not None else None

    @field_validator("name", "company", "fit_reason")
    @classmethod
    def validate_update_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must_not_be_blank")
        return value.strip() if value is not None else None

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
    search: str | None = Query(default=None, max_length=120),
    project_id: str | None = Query(default=None, max_length=40),
):
    if stage is not None and stage not in ALLOWED_STAGES:
        raise HTTPException(status_code=422, detail="invalid_prospect_stage")
    if project_id is not None and project_id != "unlinked":
        try:
            UUID(project_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid_project_filter") from None
    await _authorize(request, workspace_id, "viewer")
    store = _store(request)
    items = await store.list_prospects(
        workspace_id=workspace_id, stage=stage, limit=limit, offset=offset, search=search,
        project_id=UUID(project_id) if project_id and project_id != "unlinked" else None,
        unlinked_only=project_id == "unlinked",
    )
    total = await store.count_prospects(
        workspace_id=workspace_id, stage=stage, search=search,
        project_id=UUID(project_id) if project_id and project_id != "unlinked" else None,
        unlinked_only=project_id == "unlinked",
    )
    return {"items": items, "limit": limit, "offset": offset, "total": total, "has_more": offset + len(items) < total}


@router.get("/export.csv")
async def export_prospects_csv(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    stage: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
):
    """Export the caller's authorized workspace CRM records as a spreadsheet-safe CSV."""
    if stage is not None and stage not in ALLOWED_STAGES:
        raise HTTPException(status_code=422, detail="invalid_prospect_stage")
    await _authorize(request, workspace_id, "viewer")
    store = _store(request)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    columns = ("id", "name", "company", "role", "contact_email", "contact_phone_e164", "website_url", "evidence_url", "fit_reason", "stage", "notes", "created_at", "updated_at")
    writer.writerow(columns)
    offset = 0
    while True:
        rows = await store.list_prospects(workspace_id=workspace_id, stage=stage, limit=100, offset=offset, search=search)
        if not rows:
            break
        for row in rows:
            values = []
            for column in columns:
                value = row.get(column)
                cell = "" if value is None else str(value)
                # Prevent spreadsheet formula execution when a CSV is opened in Excel/Sheets.
                if cell.lstrip().startswith(("=", "+", "-", "@")):
                    cell = "'" + cell
                values.append(cell)
            writer.writerow(values)
        offset += len(rows)
        if len(rows) < 100:
            break
    payload = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([payload]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="outreach-prospects.csv"', "Cache-Control": "no-store"},
    )


@router.post("/import.csv")
async def import_prospects_csv(request: Request, workspace_id: str = Query(min_length=1, max_length=200)):
    """Validate and import a bounded CSV batch; duplicate evidence rows are reported, never overwritten."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "member", session)
    raw = await request.body()
    if not raw or len(raw) > 1_000_000:
        raise HTTPException(status_code=413, detail="csv_file_empty_or_too_large")
    try:
        decoded = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        required = {"name", "company", "website_url", "evidence_url", "fit_reason"}
        headers = {str(value or "").strip() for value in (reader.fieldnames or [])}
        if not required.issubset(headers):
            raise HTTPException(status_code=422, detail="csv_missing_required_columns")
        rows = list(reader)
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="csv_must_be_utf8") from None
    except csv.Error:
        raise HTTPException(status_code=422, detail="csv_format_invalid") from None
    if len(rows) > 500:
        raise HTTPException(status_code=422, detail="csv_row_limit_exceeded_500")
    store = _store(request)
    created = 0
    duplicates = 0
    invalid = []
    for index, row in enumerate(rows, start=2):
        try:
            payload = ProspectCreate.model_validate({
                "workspace_id": workspace_id,
                "name": row.get("name", ""),
                "company": row.get("company", ""),
                "role": row.get("role") or None,
                "contact_email": row.get("contact_email") or None,
                "contact_phone_e164": row.get("contact_phone_e164") or None,
                "website_url": row.get("website_url", ""),
                "evidence_url": row.get("evidence_url", ""),
                "fit_reason": row.get("fit_reason", ""),
                "verified_facts": [],
            })
            duplicate = await store.find_duplicate(
                workspace_id=workspace_id, contact_email=payload.contact_email,
                evidence_url=payload.evidence_url,
            )
            if duplicate:
                duplicates += 1
                continue
            await store.create_prospect(
                workspace_id=workspace_id, created_by=session["user_id"],
                name=payload.name, company=payload.company, role=payload.role,
                contact_email=payload.contact_email, contact_phone_e164=payload.contact_phone_e164,
                website_url=payload.website_url, evidence_url=payload.evidence_url,
                fit_reason=payload.fit_reason, verified_facts=payload.verified_facts,
            )
            created += 1
        except Exception as exc:
            if type(exc).__name__ == "UniqueViolationError":
                duplicates += 1
            elif hasattr(exc, "errors"):
                invalid.append({"row": index, "reason": "invalid_fields"})
            else:
                raise HTTPException(status_code=503, detail="prospect_import_unavailable") from None
    return {"created": created, "duplicates": duplicates, "invalid": invalid[:100], "invalid_count": len(invalid), "processed": len(rows)}


@router.post("", status_code=201)
async def create_prospect(payload: ProspectCreate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    try:
        prospect = await _store(request).create_prospect(
            workspace_id=payload.workspace_id, created_by=session["user_id"],
            name=payload.name, company=payload.company, role=payload.role,
            contact_email=payload.contact_email, contact_phone_e164=payload.contact_phone_e164,
            website_url=payload.website_url,
            evidence_url=payload.evidence_url, fit_reason=payload.fit_reason,
            verified_facts=payload.verified_facts, project_id=payload.project_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
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
    await _authorize(request, payload.workspace_id, "member", session)
    try:
        result = await _store(request).update_prospect(
            workspace_id=payload.workspace_id, prospect_id=prospect_id,
            stage=payload.stage, notes=payload.notes, name=payload.name,
            company=payload.company, role=payload.role, contact_email=payload.contact_email,
            contact_phone_e164=payload.contact_phone_e164, website_url=payload.website_url,
            evidence_url=payload.evidence_url, fit_reason=payload.fit_reason,
            project_id=payload.project_id,
            project_id_supplied="project_id" in payload.model_fields_set,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="no_prospect_updates_supplied") from None
    except Exception as exc:
        if type(exc).__name__ == "UniqueViolationError":
            raise HTTPException(status_code=409, detail="prospect_evidence_already_exists") from None
        raise HTTPException(status_code=503, detail="prospect_update_unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="prospect_not_found")
    return result


@router.put("/{prospect_id}/contact-controls")
async def update_contact_controls(prospect_id: UUID, payload: ContactControlsUpdate, request: Request):
    """Let an authorized workspace admin record suppression or documented WhatsApp opt-in."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    if payload.whatsapp_opt_in_confirmed and not payload.whatsapp_opt_in_evidence_url:
        raise HTTPException(status_code=422, detail="whatsapp_opt_in_evidence_required")
    if payload.whatsapp_opt_in_confirmed and payload.whatsapp_account_id is None:
        raise HTTPException(status_code=422, detail="whatsapp_account_required_for_consent")
    store = getattr(request.app.state, "campaign_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="contact_controls_not_configured")
    try:
        result = await store.update_contact_controls(
            workspace_id=payload.workspace_id,
            prospect_id=prospect_id,
            actor_id=session["user_id"],
            email_suppressed=payload.email_suppressed,
            whatsapp_opt_in_confirmed=payload.whatsapp_opt_in_confirmed,
            whatsapp_account_id=payload.whatsapp_account_id,
            whatsapp_opt_in_evidence_url=payload.whatsapp_opt_in_evidence_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=503, detail="contact_controls_update_unavailable") from None
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
