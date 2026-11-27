"""Workspace-authorized project profiles for multiple client websites and growth goals."""
from __future__ import annotations

import json
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="project_service_not_configured")
    return pool


async def _authorize(request: Request, workspace_id: str, role: str, session: dict) -> None:
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")


def _https_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        raise ValueError("invalid_website_url") from None
    if (parsed.scheme.lower() != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443)):
        raise ValueError("website_url_must_be_https")
    return value.strip()


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    website_url: str | None = Field(default=None, max_length=2048)
    business_model: str = Field(default="", max_length=120)
    target_market: str = Field(default="", max_length=240)
    language: str = Field(default="", max_length=120)
    audience: str = Field(default="", max_length=2000)
    offer: str = Field(default="", max_length=2000)
    conversion_goal: str = Field(default="", max_length=300)
    brand_voice: str = Field(default="", max_length=800)
    competitors: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("project_name_required")
        return value

    @field_validator("website_url")
    @classmethod
    def validate_website(cls, value: str | None) -> str | None:
        return _https_url(value)

    @field_validator("competitors")
    @classmethod
    def clean_competitors(cls, value: list[str]) -> list[str]:
        clean = []
        for item in value:
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > 500:
                raise ValueError("invalid_competitor")
            clean.append(item.strip())
        return list(dict.fromkeys(clean))


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    website_url: str | None = Field(default=None, max_length=2048)
    business_model: str | None = Field(default=None, max_length=120)
    target_market: str | None = Field(default=None, max_length=240)
    language: str | None = Field(default=None, max_length=120)
    audience: str | None = Field(default=None, max_length=2000)
    offer: str | None = Field(default=None, max_length=2000)
    conversion_goal: str | None = Field(default=None, max_length=300)
    brand_voice: str | None = Field(default=None, max_length=800)
    competitors: list[str] | None = Field(default=None, max_length=20)

    @field_validator("name")
    @classmethod
    def clean_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("project_name_required")
        return value

    @field_validator("website_url")
    @classmethod
    def validate_optional_website(cls, value: str | None) -> str | None:
        return _https_url(value)

    @field_validator("competitors")
    @classmethod
    def clean_optional_competitors(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        clean = []
        for item in value:
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > 500:
                raise ValueError("invalid_competitor")
            clean.append(item.strip())
        return list(dict.fromkeys(clean))


@router.get("")
async def list_projects(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
) -> dict:
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    try:
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, workspace_id, name, website_url, business_model, target_market,
                          language, audience, offer, conversion_goal, brand_voice, competitors,
                          status, created_by, created_at, updated_at
                   FROM workspace_projects
                   WHERE workspace_id=$1 AND archived_at IS NULL
                   ORDER BY updated_at DESC, id
                   LIMIT $2 OFFSET $3""",
                workspace_id, limit, offset,
            )
        items = []
        for row in rows:
            item = dict(row)
            item["id"] = str(item["id"])
            item["created_by"] = str(item["created_by"])
            if isinstance(item.get("competitors"), str):
                try:
                    item["competitors"] = json.loads(item["competitors"])
                except json.JSONDecodeError:
                    item["competitors"] = []
            items.append(item)
        return {"items": items, "limit": limit, "offset": offset}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="project_list_unavailable") from None


@router.post("", status_code=201)
async def create_project(payload: ProjectCreate, request: Request) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO workspace_projects
                   (workspace_id,name,website_url,business_model,target_market,language,audience,
                    offer,conversion_goal,brand_voice,competitors,created_by)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12)
                   RETURNING id,workspace_id,name,website_url,business_model,target_market,language,
                             audience,offer,conversion_goal,brand_voice,competitors,status,created_by,
                             created_at,updated_at""",
                payload.workspace_id, payload.name, payload.website_url, payload.business_model.strip(),
                payload.target_market.strip(), payload.language.strip(), payload.audience.strip(),
                payload.offer.strip(), payload.conversion_goal.strip(), payload.brand_voice.strip(),
                json.dumps(payload.competitors), UUID(str(session["user_id"])),
            )
        result = dict(row)
        result["id"] = str(result["id"])
        result["created_by"] = str(result["created_by"])
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="project_create_unavailable") from None


@router.patch("/{project_id}")
async def update_project(project_id: UUID, payload: ProjectUpdate, request: Request) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    changes = payload.model_dump(exclude_unset=True, exclude={"workspace_id"})
    if not changes:
        raise HTTPException(status_code=422, detail="no_project_updates_supplied")
    columns = {
        "name": "name",
        "website_url": "website_url",
        "business_model": "business_model",
        "target_market": "target_market",
        "language": "language",
        "audience": "audience",
        "offer": "offer",
        "conversion_goal": "conversion_goal",
        "brand_voice": "brand_voice",
        "competitors": "competitors",
    }
    assignments = []
    values = [project_id, payload.workspace_id]
    for field, value in changes.items():
        column = columns[field]
        if value is None and field not in {"website_url", "competitors"}:
            raise HTTPException(status_code=422, detail="project_field_cannot_be_null")
        if field == "competitors" and value is None:
            value = []
        if field == "competitors":
            value = json.dumps(value)
        values.append(value)
        placeholder = "$" + str(len(values))
        assignments.append(f"{column}={placeholder}::jsonb" if field == "competitors" else f"{column}={placeholder}")
    assignments.append("updated_at=now()")
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE workspace_projects SET " + ", ".join(assignments) +
                " WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL RETURNING "
                "id,workspace_id,name,website_url,business_model,target_market,language,audience,"
                "offer,conversion_goal,brand_voice,competitors,status,created_by,created_at,updated_at",
                *values,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="project_not_found")
        result = dict(row)
        result["id"] = str(result["id"])
        result["created_by"] = str(result["created_by"])
        return result
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="project_update_unavailable") from None


@router.delete("/{project_id}", status_code=204)
async def archive_project(project_id: UUID, request: Request, workspace_id: str = Query(min_length=1, max_length=200)) -> None:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin", session)
    try:
        async with _pool(request).acquire() as conn:
            result = await conn.execute(
                """UPDATE workspace_projects SET status='archived',archived_at=now(),updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL""",
                project_id, workspace_id,
            )
    except Exception:
        raise HTTPException(status_code=503, detail="project_archive_unavailable") from None
    if not result.endswith(" 1"):
        raise HTTPException(status_code=404, detail="project_not_found")
