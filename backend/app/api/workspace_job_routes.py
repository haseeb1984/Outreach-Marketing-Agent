"""Workspace-scoped job status and cancellation endpoints.

No public job enqueue or execution endpoint is exposed here. New scan submission
stays disabled until the production SSRF egress release gate is satisfied.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.auth_routes import _authenticated, _check_csrf, _consume

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/jobs", tags=["workspace jobs"])


async def _authorized_queue(request: Request, workspace_id: str, minimum_role: str):
    store, _, session = await _authenticated(request)
    if not isinstance(workspace_id, str) or not workspace_id.strip() or len(workspace_id) > 200:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    try:
        allowed = await store.authorize_workspace(
            user_id=session["user_id"],
            workspace_id=workspace_id,
            minimum_role=minimum_role,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_authorization_unavailable") from None
    if not allowed:
        raise HTTPException(status_code=404, detail="workspace_not_found")
    queue = getattr(request.app.state, "workspace_job_queue", None)
    if queue is None:
        raise HTTPException(status_code=503, detail="workspace_jobs_unavailable")
    limiter = getattr(request.app.state, "auth_rate_limiter", None)
    if limiter is None:
        raise HTTPException(status_code=503, detail="workspace_jobs_unavailable")
    return queue, session, limiter


@router.get("")
async def list_workspace_jobs(
    workspace_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = None,
):
    queue, session, limiter = await _authorized_queue(request, workspace_id, "viewer")
    await _consume(
        limiter,
        namespace="workspace-job-list",
        identifier=f"{workspace_id}:{session['user_id']}",
        limit=120,
        window=3600,
    )
    try:
        jobs = await queue.list_for_workspace(
            workspace_id=workspace_id, limit=limit, before=before
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_job_query") from None
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_jobs_unavailable") from None
    return {"workspace_id": workspace_id, "jobs": jobs}


@router.get("/{job_id}")
async def get_workspace_job(
    workspace_id: str, job_id: UUID, request: Request
):
    queue, session, limiter = await _authorized_queue(request, workspace_id, "viewer")
    await _consume(
        limiter,
        namespace="workspace-job-status",
        identifier=f"{workspace_id}:{session['user_id']}",
        limit=120,
        window=3600,
    )
    try:
        job = await queue.get_status(workspace_id=workspace_id, job_id=job_id)
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_jobs_unavailable") from None
    if job is None:
        raise HTTPException(status_code=404, detail="workspace_job_not_found")
    return {"workspace_id": workspace_id, "job": job}


@router.post("/{job_id}/cancel")
async def cancel_workspace_job(
    workspace_id: str, job_id: UUID, request: Request
):
    queue, session, limiter = await _authorized_queue(request, workspace_id, "member")
    _check_csrf(request, session)
    await _consume(
        limiter,
        namespace="workspace-job-cancel",
        identifier=f"{workspace_id}:{session['user_id']}",
        limit=30,
        window=3600,
    )
    try:
        cancelled = await queue.cancel(workspace_id=workspace_id, job_id=job_id)
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_jobs_unavailable") from None
    if not cancelled:
        raise HTTPException(status_code=404, detail="queued_workspace_job_not_found")
    return {"workspace_id": workspace_id, "job_id": str(job_id), "status": "cancelled"}
