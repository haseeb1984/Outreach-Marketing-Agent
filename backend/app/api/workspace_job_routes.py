"""Authenticated API for durable, workspace-scoped website growth jobs."""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.services.workspace_job_queue import WorkspaceJobQueue

router = APIRouter(prefix="/api/v1/workspace-jobs", tags=["workspace jobs"])


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="workspace_job_service_not_configured")
    return pool


async def _authorize(request: Request, workspace_id: str, role: str, session: dict) -> None:
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role=role
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")


def _normalize_start_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except (AttributeError, ValueError):
        raise ValueError("website_url_must_be_https") from None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ValueError("website_url_must_be_https")
    # URLs placed in durable job payloads must not retain query strings/fragments,
    # which can accidentally contain credentials or one-time tokens.
    return urlunsplit(("https", parsed.netloc, parsed.path or "/", "", ""))


class WebsiteGrowthScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    start_url: str = Field(min_length=9, max_length=2048)
    business_type: str = Field(min_length=1, max_length=160)
    target_market: str = Field(min_length=1, max_length=160)
    target_queries: list[str] = Field(default_factory=list, max_length=20)
    max_pages: int = Field(default=10, ge=1, le=10, strict=True)
    max_depth: int = Field(default=2, ge=0, le=2, strict=True)

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


@router.post("/website-growth-scan", status_code=202)
async def enqueue_website_growth_scan(
    payload: WebsiteGrowthScanRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=160),
) -> dict:
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    await _authorize(request, payload.workspace_id, "member", session)

    domain_store = getattr(request.app.state, "domain_authorization_store", None)
    if domain_store is None:
        raise HTTPException(status_code=503, detail="domain_authorization_not_configured")
    try:
        await domain_store.authorize_url(
            workspace_id=payload.workspace_id, url=payload.start_url
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="website_domain_not_authorized") from None
    except Exception:
        raise HTTPException(status_code=503, detail="domain_authorization_unavailable") from None

    subscriptions = getattr(request.app.state, "subscription_store", None)
    if subscriptions is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    try:
        reservation = await subscriptions.reserve_usage(
            workspace_id=payload.workspace_id,
            feature="website_audits",
            idempotency_key="workspace-growth-job:" + idempotency_key,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    if not reservation.get("allowed"):
        reason = reservation.get("reason", "entitlement_denied")
        raise HTTPException(status_code=429 if reason == "quota_exhausted" else 403, detail=reason)
    if reservation.get("status") == "consumed":
        raise HTTPException(status_code=409, detail="growth_job_key_already_used")
    reservation_id = reservation["reservation_id"]

    try:
        job = await WorkspaceJobQueue(_pool(request)).enqueue(
            workspace_id=payload.workspace_id,
            job_type="website_growth_scan",
            payload={
                "start_url": payload.start_url,
                "business_type": payload.business_type,
                "target_market": payload.target_market,
                "target_queries": payload.target_queries,
                "requested_by": str(session["user_id"]),
                "max_pages": payload.max_pages,
                "max_depth": payload.max_depth,
            },
            idempotency_key=idempotency_key,
            max_attempts=3,
        )
    except ValueError:
        try:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
            )
        except Exception:
            pass
        raise HTTPException(status_code=422, detail="invalid_website_growth_job") from None
    except Exception:
        try:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="released"
            )
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="website_growth_job_unavailable") from None
    if reservation.get("status") == "reserved":
        try:
            finished = await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
        except Exception:
            finished = False
        if not finished:
            raise HTTPException(status_code=503, detail="growth_job_quota_persistence_failed")
    return {
        "id": job["id"],
        "workspace_id": job["workspace_id"],
        "job_type": job["job_type"],
        "status": job["status"],
        "attempt_count": job["attempt_count"],
        "max_attempts": job["max_attempts"],
        "run_after": job["run_after"],
        "created_at": job["created_at"],
    }


@router.get("")
async def list_workspace_jobs(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict:
    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    try:
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, workspace_id, job_type, status, error_code,
                          attempt_count, max_attempts, run_after, created_at,
                          started_at, finished_at, updated_at
                   FROM workspace_jobs
                   WHERE workspace_id=$1
                   ORDER BY created_at DESC, id DESC
                   LIMIT $2 OFFSET $3""",
                workspace_id, limit, offset,
            )
            total = await conn.fetchval(
                "SELECT count(*) FROM workspace_jobs WHERE workspace_id=$1",
                workspace_id,
            )
        return {
            "items": [
                {**dict(row), "id": str(row["id"])}
                for row in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_job_list_unavailable") from None


@router.get("/{job_id}")
async def get_workspace_job(
    job_id: str,
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
) -> dict:
    """Return a job's outcome only after proving membership in its owning workspace."""
    from uuid import UUID

    _, _, session = await _authenticated(request)
    await _authorize(request, workspace_id, "viewer", session)
    try:
        parsed_job_id = UUID(job_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="workspace_job_not_found") from None
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, workspace_id, job_type, status, result, error_code,
                          attempt_count, max_attempts, run_after, created_at,
                          started_at, finished_at, updated_at
                   FROM workspace_jobs
                   WHERE id=$1 AND workspace_id=$2""",
                parsed_job_id, workspace_id,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="workspace_job_not_found")
        item = dict(row)
        item["id"] = str(item["id"])
        # Research output is visible only for completed jobs; never expose internal
        # payloads or lease/worker metadata through this customer-facing endpoint.
        if item["status"] != "succeeded":
            item["result"] = None
        return item
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="workspace_job_unavailable") from None
