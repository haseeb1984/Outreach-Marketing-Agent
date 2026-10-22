"""Authenticated, quota-controlled read-only website audits for verified workspace domains."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
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
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
        )
        return {
            "workspace_id": payload.workspace_id,
            "report": report,
            "persisted": False,
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
