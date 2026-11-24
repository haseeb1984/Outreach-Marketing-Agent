"""Workspace-scoped editorial briefs derived from saved website growth reports.

Approval is an editorial checkpoint only. This module never publishes content or
writes to a customer's CMS.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf

router = APIRouter(prefix="/api/v1/content-briefs", tags=["content workflow"])


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="content_brief_service_not_configured")
    return pool


async def _authorize(request: Request, workspace_id: str, role: str, session: dict) -> None:
    store = getattr(request.app.state, "auth_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await store.authorize_workspace(user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role):
        raise HTTPException(status_code=404, detail="workspace_not_found")


def _serialize(row: dict) -> dict:
    for key in ("id", "project_id", "report_id", "created_by", "reviewed_by"):
        if row.get(key) is not None:
            row[key] = str(row[key])
    return row


class BriefCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    project_id: UUID
    report_id: UUID
    action_id: str = Field(min_length=1, max_length=160)


class BriefUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    brief: str = Field(min_length=1, max_length=10000)
    target_keyword: str = Field(default="", max_length=300)
    status: str = "draft"

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"draft", "in_review"}:
            raise ValueError("invalid_content_brief_status")
        return value

    @field_validator("title", "brief")
    @classmethod
    def clean_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content_brief_field_required")
        return value.strip()


class BriefReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    decision: str
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, value: str) -> str:
        if value not in {"approved", "rejected"}:
            raise ValueError("invalid_review_decision")
        return value


@router.get("")
async def list_content_briefs(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
):
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    try:
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT id,workspace_id,project_id,report_id,action_id,title,brief,
                          target_keyword,evidence_url,status,created_by,reviewed_by,
                          review_note,created_at,updated_at,reviewed_at
                   FROM website_content_briefs WHERE workspace_id=$1
                   ORDER BY updated_at DESC,id DESC LIMIT $2""",
                workspace_id, limit,
            )
        return {"items": [_serialize(dict(row)) for row in rows]}
    except Exception:
        raise HTTPException(status_code=503, detail="content_brief_list_unavailable") from None


@router.post("", status_code=201)
async def create_content_brief(payload: BriefCreate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    try:
        async with _pool(request).acquire() as conn:
            async with conn.transaction():
                project_row = await conn.fetchrow(
                    "SELECT id FROM workspace_projects WHERE id=$1 AND workspace_id=$2 AND archived_at IS NULL",
                    payload.project_id, payload.workspace_id,
                )
                if project_row is None:
                    raise HTTPException(status_code=404, detail="project_not_found")
                report_row = await conn.fetchrow(
                    """SELECT report FROM website_audit_reports
                       WHERE id=$1 AND workspace_id=$2""",
                    payload.report_id, payload.workspace_id,
                )
                if report_row is None:
                    raise HTTPException(status_code=404, detail="growth_report_not_found")
                report = report_row["report"]
                if isinstance(report, str):
                    report = json.loads(report)
                if str(report.get("project_id") or "") != str(payload.project_id):
                    raise HTTPException(status_code=422, detail="growth_report_project_mismatch")
                actions = (report.get("strategy") or {}).get("actions") or []
                action = next((item for item in actions if isinstance(item, dict) and item.get("id") == payload.action_id), None)
                if action is None:
                    raise HTTPException(status_code=404, detail="growth_recommendation_not_found")
                title = str(action.get("title") or "Website content task").strip()[:300]
                recommended = str(action.get("recommended_action") or "").strip()
                if not recommended:
                    raise HTTPException(status_code=422, detail="recommendation_has_no_content_brief")
                evidence = str(action.get("evidence_url") or "")[:2048]
                keyword = str(action.get("target_keyword") or action.get("query") or "")[:300]
                row = await conn.fetchrow(
                    """INSERT INTO website_content_briefs
                       (workspace_id,project_id,report_id,action_id,title,brief,target_keyword,
                        evidence_url,created_by)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                       ON CONFLICT (workspace_id,report_id,action_id) DO NOTHING
                       RETURNING *""",
                    payload.workspace_id, payload.project_id, payload.report_id, payload.action_id,
                    title, recommended, keyword, evidence, UUID(str(session["user_id"])),
                )
                if row is None:
                    row = await conn.fetchrow(
                        """SELECT * FROM website_content_briefs
                           WHERE workspace_id=$1 AND report_id=$2 AND action_id=$3""",
                        payload.workspace_id, payload.report_id, payload.action_id,
                    )
        return _serialize(dict(row))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="content_brief_create_unavailable") from None


@router.patch("/{brief_id}")
async def update_content_brief(brief_id: UUID, payload: BriefUpdate, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE website_content_briefs SET title=$3,brief=$4,target_keyword=$5,
                          status=$6,updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND status IN ('draft','rejected')
                   RETURNING *""",
                brief_id, payload.workspace_id, payload.title, payload.brief,
                payload.target_keyword.strip(), payload.status,
            )
        if row is None:
            raise HTTPException(status_code=409, detail="content_brief_not_editable")
        return _serialize(dict(row))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="content_brief_update_unavailable") from None


@router.post("/{brief_id}/review")
async def review_content_brief(brief_id: UUID, payload: BriefReview, request: Request):
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "admin", session)
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE website_content_briefs SET status=$3,reviewed_by=$4,
                          review_note=$5,reviewed_at=now(),updated_at=now()
                   WHERE id=$1 AND workspace_id=$2 AND status='in_review'
                   RETURNING *""",
                brief_id, payload.workspace_id, payload.decision,
                UUID(str(session["user_id"])), payload.note,
            )
        if row is None:
            raise HTTPException(status_code=409, detail="content_brief_not_pending_review")
        return _serialize(dict(row))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="content_brief_review_unavailable") from None
