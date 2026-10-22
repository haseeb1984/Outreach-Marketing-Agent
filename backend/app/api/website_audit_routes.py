"""Authenticated, quota-controlled read-only website audits for verified workspace domains."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth_routes import _authenticated, _check_csrf
from app.services.website_discovery import discover_and_crawl
from app.services.website_fetch import FetchLimits

router = APIRouter(prefix="/api/v1/website-audits", tags=["website growth"])


class WebsiteAuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    start_url: str = Field(min_length=8, max_length=2048)
    max_pages: int = Field(default=5, ge=1, le=8)
    idempotency_key: str = Field(min_length=8, max_length=180, pattern=r"^[A-Za-z0-9._:-]+$")


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
