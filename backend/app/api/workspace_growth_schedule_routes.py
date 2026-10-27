"""CRUD for recurring website-growth scans; schedules never send outreach."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.api.workspace_job_routes import _normalize_start_url

router = APIRouter(prefix="/api/v1/workspace-growth-schedules", tags=["workspace growth schedules"])


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="growth_schedule_service_not_configured")
    return pool


async def _authorize(request: Request, workspace_id: str, role: str, session: dict) -> None:
    store = getattr(request.app.state, "auth_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")


class GrowthScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    start_url: str = Field(min_length=9, max_length=2048)
    business_type: str = Field(min_length=1, max_length=160)
    target_market: str = Field(min_length=1, max_length=160)
    target_queries: list[str] = Field(default_factory=list, max_length=20)
    max_pages: int = Field(default=10, ge=1, le=10, strict=True)
    max_depth: int = Field(default=2, ge=0, le=2, strict=True)
    interval_hours: int = Field(default=168, ge=6, le=720, strict=True)

    @field_validator("start_url")
    @classmethod
    def clean_url(cls, value: str) -> str:
        return _normalize_start_url(value)

    @field_validator("business_type", "target_market")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field_required")
        return value

    @field_validator("target_queries")
    @classmethod
    def clean_queries(cls, value: list[str]) -> list[str]:
        clean = []
        for query in value:
            query = query.strip() if isinstance(query, str) else ""
            if not query or len(query) > 200:
                raise ValueError("invalid_target_query")
            clean.append(query)
        return list(dict.fromkeys(clean))


class GrowthScheduleStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"active", "paused"}:
            raise ValueError("invalid_schedule_status")
        return value


def _serialize(row: dict) -> dict:
    item = dict(row)
    item["id"] = str(item["id"])
    item["created_by"] = str(item["created_by"])
    return item


@router.post("", status_code=201)
async def create_growth_schedule(payload: GrowthScheduleCreate, request: Request) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    domain_store = getattr(request.app.state, "domain_authorization_store", None)
    if domain_store is None:
        raise HTTPException(status_code=503, detail="domain_authorization_not_configured")
    try:
        await domain_store.authorize_url(workspace_id=payload.workspace_id, url=payload.start_url)
    except ValueError:
        raise HTTPException(status_code=422, detail="website_domain_not_authorized") from None
    except Exception:
        raise HTTPException(status_code=503, detail="domain_authorization_unavailable") from None

    job_payload = {
        "start_url": payload.start_url,
        "business_type": payload.business_type,
        "target_market": payload.target_market,
        "target_queries": payload.target_queries,
        "max_pages": payload.max_pages,
        "max_depth": payload.max_depth,
    }
    try:
        async with _pool(request).acquire() as conn:
            async with conn.transaction():
                # Serialize schedule creation per workspace before enforcing the cap.
                await conn.fetchrow(
                    "SELECT id FROM workspaces WHERE id=$1 FOR UPDATE",
                    payload.workspace_id,
                )
                active_count = await conn.fetchval(
                    "SELECT count(*) FROM workspace_growth_schedules WHERE workspace_id=$1 AND status='active'",
                    payload.workspace_id,
                )
                if active_count >= 20:
                    raise HTTPException(status_code=429, detail="growth_schedule_limit_reached")
                row = await conn.fetchrow(
                    """INSERT INTO workspace_growth_schedules
                       (workspace_id, payload, interval_hours, status, next_run_at, created_by)
                       VALUES ($1, $2::jsonb, $3, 'active', now(), $4)
                       RETURNING id, workspace_id, interval_hours, status, next_run_at,
                                 last_enqueued_at, created_by, created_at, updated_at""",
                    payload.workspace_id, json.dumps(job_payload), payload.interval_hours,
                    UUID(str(session["user_id"])),
                )
        return _serialize(dict(row))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="growth_schedule_create_unavailable") from None


@router.get("")
async def list_growth_schedules(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    try:
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, workspace_id, interval_hours, status, next_run_at,
                          last_enqueued_at, created_by, created_at, updated_at
                   FROM workspace_growth_schedules
                   WHERE workspace_id=$1
                   ORDER BY created_at DESC, id DESC""",
                workspace_id,
            )
        return {"items": [_serialize(dict(row)) for row in rows]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="growth_schedule_list_unavailable") from None


@router.patch("/{schedule_id}")
async def update_growth_schedule(
    schedule_id: UUID,
    payload: GrowthScheduleStatusUpdate,
    request: Request,
) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    try:
        async with _pool(request).acquire() as conn:
            async with conn.transaction():
                await conn.fetchrow(
                    "SELECT id FROM workspaces WHERE id=$1 FOR UPDATE",
                    payload.workspace_id,
                )
                current_status = await conn.fetchval(
                    "SELECT status FROM workspace_growth_schedules WHERE id=$1 AND workspace_id=$2 FOR UPDATE",
                    schedule_id, payload.workspace_id,
                )
                if current_status is None:
                    raise HTTPException(status_code=404, detail="growth_schedule_not_found")
                if current_status != "active" and payload.status == "active":
                    active_count = await conn.fetchval(
                        "SELECT count(*) FROM workspace_growth_schedules WHERE workspace_id=$1 AND status='active'",
                        payload.workspace_id,
                    )
                    if active_count >= 20:
                        raise HTTPException(status_code=429, detail="growth_schedule_limit_reached")
                row = await conn.fetchrow(
                    """UPDATE workspace_growth_schedules
                       SET status=$3, updated_at=now()
                       WHERE id=$1 AND workspace_id=$2
                       RETURNING id, workspace_id, interval_hours, status, next_run_at,
                                 last_enqueued_at, created_by, created_at, updated_at""",
                    schedule_id, payload.workspace_id, payload.status,
                )
        if row is None:
            raise HTTPException(status_code=404, detail="growth_schedule_not_found")
        return _serialize(dict(row))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="growth_schedule_update_unavailable") from None


@router.delete("/{schedule_id}", status_code=204)
async def delete_growth_schedule(
    schedule_id: UUID,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> None:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, workspace_id, "admin", session)
    try:
        async with _pool(request).acquire() as conn:
            result = await conn.execute(
                "DELETE FROM workspace_growth_schedules WHERE id=$1 AND workspace_id=$2",
                schedule_id, workspace_id,
            )
        if not result.endswith(" 1"):
            raise HTTPException(status_code=404, detail="growth_schedule_not_found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="growth_schedule_delete_unavailable") from None
