"""Quota-controlled public-web search for evidence-backed prospect discovery.

Search results are suggestions only: they are not automatically added to the CRM and
must be reviewed by a person. The provider credential is read from server environment.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings

router = APIRouter(prefix="/api/v1/research", tags=["prospect research"])


class ProspectSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=3, max_length=400)
    count: int = Field(default=10, ge=1, le=20)
    idempotency_key: str = Field(min_length=8, max_length=180, pattern=r"^[A-Za-z0-9._:-]+$")


def _public_https_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme.lower() != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            return None
        host = parsed.hostname.lower().rstrip(".")
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local") or host.endswith(".internal"):
            return None
        if host.replace(".", "").isdigit():
            return None
        return value
    except ValueError:
        return None


@router.post("/prospects/search")
async def search_public_prospects(payload: ProspectSearchInput, request: Request) -> dict:
    """Search public web results with evidence links; does not persist or contact prospects."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=payload.workspace_id, minimum_role="member"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    if not settings.brave_search_api_key or not settings.brave_search_api_key.strip():
        raise HTTPException(status_code=503, detail="search_provider_not_configured")
    subscriptions = getattr(request.app.state, "subscription_store", None)
    if subscriptions is None:
        raise HTTPException(status_code=503, detail="billing_service_not_configured")

    try:
        reservation = await subscriptions.reserve_usage(
            workspace_id=payload.workspace_id,
            feature="prospect_research",
            idempotency_key="prospect-research:" + payload.idempotency_key,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="billing_status_unavailable") from None
    if not reservation.get("allowed"):
        reason = reservation.get("reason", "entitlement_denied")
        raise HTTPException(status_code=429 if reason == "quota_exhausted" else 403, detail=reason)
    if reservation.get("reason") == "idempotent_replay" or reservation.get("status") == "consumed":
        raise HTTPException(status_code=409, detail="research_key_already_used")

    reservation_id = reservation["reservation_id"]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0), follow_redirects=False) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": payload.query.strip(), "count": payload.count, "safesearch": "moderate"},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": settings.brave_search_api_key,
                },
            )
        if response.status_code != 200:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
            raise HTTPException(status_code=502, detail="search_provider_unavailable")
        data = response.json()
        web = data.get("web") if isinstance(data, dict) else None
        raw_results = web.get("results") if isinstance(web, dict) else None
        if not isinstance(raw_results, list):
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
            raise HTTPException(status_code=502, detail="search_response_invalid")
        results = []
        seen = set()
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = _public_https_url(item.get("url"))
            title = item.get("title")
            description = item.get("description")
            if not url or url in seen or not isinstance(title, str) or not title.strip():
                continue
            seen.add(url)
            results.append({
                "title": title.strip()[:300],
                "url": url,
                "description": description.strip()[:1200] if isinstance(description, str) else "",
                "evidence_type": "public_search_result",
                "requires_human_review": True,
            })
            if len(results) >= payload.count:
                break
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
        )
        return {
            "workspace_id": payload.workspace_id,
            "query": payload.query.strip(),
            "provider": "brave_search",
            "items": results,
            "count": len(results),
            "persisted_to_crm": False,
            "notice": "Search results are unverified leads. Review each source and establish fit before saving or contacting anyone.",
        }
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        # The provider request was attempted, so consume the quota to prevent retry-based cost bypass.
        try:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="search_provider_unavailable") from None
