"""Authenticated, quota-controlled read-only website audits for verified workspace domains."""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.services.website_discovery import discover_and_crawl
from app.services.website_fetch import FetchLimits

router = APIRouter(prefix="/api/v1/website-audits", tags=["website growth"])


def _pool(request: Request):
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="website_audit_service_not_configured")
    return pool


class WebsiteAuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    start_url: str = Field(min_length=8, max_length=2048)
    max_pages: int = Field(default=5, ge=1, le=8)
    idempotency_key: str = Field(min_length=8, max_length=180, pattern=r"^[A-Za-z0-9._:-]+$")

    @field_validator("start_url")
    @classmethod
    def require_https(cls, value: str) -> str:
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


class WebsiteGrowthReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    project_id: UUID
    target_queries: list[str] = Field(min_length=1, max_length=20)
    max_pages: int = Field(default=8, ge=1, le=8)
    idempotency_key: str = Field(min_length=8, max_length=180, pattern=r"^[A-Za-z0-9._:-]+$")

    @field_validator("target_queries")
    @classmethod
    def validate_target_queries(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if isinstance(value, str) and value.strip()))
        if not cleaned or len(cleaned) > 20 or any(len(value) > 200 for value in cleaned):
            raise ValueError("target_queries_invalid")
        return cleaned


@router.get("")
async def list_website_audits(
    request: Request,
    workspace_id: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    _, _, session = await _authenticated(request)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role="viewer"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    try:
        async with _pool(request).acquire() as conn:
            rows = await conn.fetch(
                """SELECT id,workspace_id,start_url,status,created_at
                   FROM website_audit_reports WHERE workspace_id=$1
                   ORDER BY created_at DESC,id DESC LIMIT $2""",
                workspace_id, limit,
            )
        return {"items": [{**dict(row), "id": str(row["id"])} for row in rows]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="website_audit_history_unavailable") from None


@router.get("/{report_id}")
async def get_website_audit(report_id: UUID, request: Request, workspace_id: str = Query(min_length=1, max_length=200)) -> dict:
    _, _, session = await _authenticated(request)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=workspace_id, minimum_role="viewer"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    try:
        async with _pool(request).acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id,workspace_id,start_url,status,report,created_at
                   FROM website_audit_reports WHERE id=$1 AND workspace_id=$2""",
                report_id, workspace_id,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="website_audit_not_found")
        report = row["report"]
        if isinstance(report, str):
            report = json.loads(report)
        return {"report_id": str(row["id"]), "workspace_id": row["workspace_id"],
                "start_url": row["start_url"], "status": row["status"],
                "report": report, "created_at": row["created_at"]}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="website_audit_read_unavailable") from None


@router.post("")
async def create_website_audit(payload: WebsiteAuditRequest, request: Request) -> dict:
    """Audit a verified domain without modifying the target website."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=payload.workspace_id, minimum_role="member"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")

    domain_store = getattr(request.app.state, "domain_authorization_store", None)
    if domain_store is None:
        raise HTTPException(status_code=503, detail="domain_authorization_not_configured")
    try:
        await domain_store.authorize_url(workspace_id=payload.workspace_id, url=payload.start_url)
    except ValueError:
        raise HTTPException(status_code=403, detail="domain_not_verified") from None
    except Exception:
        raise HTTPException(status_code=503, detail="domain_authorization_unavailable") from None

    subscriptions = getattr(request.app.state, "subscription_store", None)
    if subscriptions is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    try:
        reservation = await subscriptions.reserve_usage(
            workspace_id=payload.workspace_id,
            feature="website_audits",
            idempotency_key="website-audit:" + payload.idempotency_key,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    if not reservation.get("allowed"):
        reason = reservation.get("reason", "entitlement_denied")
        raise HTTPException(status_code=429 if reason == "quota_exhausted" else 403, detail=reason)
    if reservation.get("reason") == "idempotent_replay" or reservation.get("status") == "consumed":
        raise HTTPException(status_code=409, detail="website_audit_key_already_used")

    reservation_id = reservation["reservation_id"]
    try:
        # Bound the synchronous API path for serverless runtimes. Larger audits should
        # move to a durable worker rather than increasing this request timeout.
        async with asyncio.timeout(18):
            report = await discover_and_crawl(
                payload.start_url,
                max_pages=payload.max_pages,
                max_depth=1,
                max_sitemaps=2,
                limits=FetchLimits(timeout_seconds=3.0, max_redirects=2, max_bytes=400_000),
            )
        async with _pool(request).acquire() as conn:
            saved = await conn.fetchrow(
                """INSERT INTO website_audit_reports
                   (workspace_id,start_url,status,report,requested_by)
                   VALUES ($1,$2,$3,$4::jsonb,$5)
                   RETURNING id,created_at""",
                payload.workspace_id, report["start_url"],
                "crawl_skipped" if report.get("crawl_skipped") else "completed",
                json.dumps(report, ensure_ascii=False),
                UUID(str(session["user_id"])),
            )
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
        )
        return {
            "report_id": str(saved["id"]),
            "workspace_id": payload.workspace_id,
            "report": report,
            "persisted": True,
            "created_at": saved["created_at"].isoformat(),
            "notice": "Read-only audit of a verified domain. Findings are observations and recommendations, not proof of search indexing or ranking outcomes.",
        }
    except TimeoutError:
        try:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
        except Exception:
            pass
        raise HTTPException(status_code=504, detail="website_audit_timed_out") from None
    except HTTPException:
        raise
    except (ValueError, OSError):
        try:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
        except Exception:
            pass
        raise HTTPException(status_code=422, detail="website_audit_input_or_fetch_rejected") from None
    except Exception:
        try:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="website_audit_unavailable") from None


@router.post("/growth-review")
async def create_website_growth_review(payload: WebsiteGrowthReviewRequest, request: Request) -> dict:
    """Build and persist an evidence-led growth plan for a verified project website."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=payload.workspace_id, minimum_role="member"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    domain_store = getattr(request.app.state, "domain_authorization_store", None)
    if domain_store is None:
        raise HTTPException(status_code=503, detail="domain_authorization_not_configured")
    pool = _pool(request)
    try:
        async with pool.acquire() as conn:
            project = await conn.fetchrow(
                """SELECT id,workspace_id,name,website_url,business_model,target_market
                   FROM workspace_projects WHERE id=$1 AND workspace_id=$2""",
                payload.project_id, payload.workspace_id,
            )
        if project is None:
            raise HTTPException(status_code=404, detail="project_not_found")
        start_url = str(project["website_url"] or "").strip()
        if not start_url:
            raise HTTPException(status_code=422, detail="project_website_required")
        await domain_store.authorize_url(workspace_id=payload.workspace_id, url=start_url)
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=403, detail="domain_not_verified") from None
    except Exception:
        raise HTTPException(status_code=503, detail="growth_review_project_unavailable") from None
    subscriptions = getattr(request.app.state, "subscription_store", None)
    if subscriptions is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")
    try:
        reservation = await subscriptions.reserve_usage(
            workspace_id=payload.workspace_id, feature="website_audits",
            idempotency_key="website-growth-review:" + payload.idempotency_key,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    if not reservation.get("allowed"):
        reason = reservation.get("reason", "entitlement_denied")
        raise HTTPException(status_code=429 if reason == "quota_exhausted" else 403, detail=reason)
    if reservation.get("reason") == "idempotent_replay" or reservation.get("status") == "consumed":
        raise HTTPException(status_code=409, detail="growth_review_key_already_used")
    reservation_id = reservation["reservation_id"]
    try:
        from app.services.persisted_website_growth_pipeline import discover_persisted_workspace_site
        async with asyncio.timeout(18):
            report = await discover_persisted_workspace_site(
                start_url, workspace_id=payload.workspace_id, domain_store=domain_store,
                business_type=str(project["business_model"] or "").strip(),
                target_market=str(project["target_market"] or "").strip(),
                target_queries=payload.target_queries, max_pages=payload.max_pages,
                max_depth=1, max_sitemaps=2,
                limits=FetchLimits(timeout_seconds=3.0, max_redirects=2, max_bytes=400_000),
            )
        status = "crawl_skipped" if report.get("status") == "crawl_skipped" else "completed"
        async with pool.acquire() as conn:
            saved = await conn.fetchrow(
                """INSERT INTO website_audit_reports
                   (workspace_id,start_url,status,report,requested_by)
                   VALUES ($1,$2,$3,$4::jsonb,$5) RETURNING id,created_at""",
                payload.workspace_id, report["start_url"], status,
                json.dumps(report, ensure_ascii=False), UUID(str(session["user_id"])),
            )
        finished = await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
        )
        if not finished:
            raise HTTPException(status_code=503, detail="growth_review_quota_persistence_failed")
        return {
            "report_id": str(saved["id"]), "workspace_id": payload.workspace_id,
            "project_id": str(payload.project_id), "project_name": project["name"],
            "report": report, "persisted": True, "created_at": saved["created_at"].isoformat(),
            "notice": "Evidence-led recommendations are saved for human review. The target website was not changed and rankings or traffic gains are not guaranteed.",
        }
    except TimeoutError:
        try:
            await subscriptions.finish_reservation(workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed")
        except Exception:
            pass
        raise HTTPException(status_code=504, detail="growth_review_timed_out") from None
    except HTTPException:
        raise
    except (ValueError, OSError):
        try:
            await subscriptions.finish_reservation(workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed")
        except Exception:
            pass
        raise HTTPException(status_code=422, detail="growth_review_input_or_fetch_rejected") from None
    except Exception:
        try:
            await subscriptions.finish_reservation(workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed")
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="growth_review_unavailable") from None
