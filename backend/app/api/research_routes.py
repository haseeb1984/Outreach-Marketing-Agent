"""Quota-controlled, evidence-ranked public-web prospect discovery.

Search results are suggestions only: they are not automatically added to the CRM and
must be reviewed by a person. Relevance scores are transparent text-match heuristics,
not lead-conversion predictions. The provider credential is read from server environment.
"""
from __future__ import annotations

import re
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


def _search_terms(value: str) -> set[str]:
    """Normalize words while ignoring short, low-information tokens."""
    return {term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) >= 3}


def _relevance(query: str, title: str, description: str) -> tuple[int, list[str]]:
    """Return a bounded, explainable lexical-match score (not a business-fit prediction)."""
    query_terms = _search_terms(query)
    if not query_terms:
        return 0, []
    title_terms = _search_terms(title)
    description_terms = _search_terms(description)
    title_matches = sorted(query_terms & title_terms)
    description_matches = sorted(query_terms & description_terms)
    # Title matches carry more weight than snippet matches; repeated words do not inflate it.
    score = round(100 * (
        0.7 * len(title_matches) / len(query_terms)
        + 0.3 * len(description_matches) / len(query_terms)
    ))
    reasons = []
    if title_matches:
        reasons.append("Title matches: " + ", ".join(title_matches))
    if description_matches:
        reasons.append("Description matches: " + ", ".join(description_matches))
    return min(100, max(0, score)), reasons


@router.post("/prospects/search")
async def search_public_prospects(payload: ProspectSearchInput, request: Request) -> dict:
    """Search public web results with relevance hints and evidence links; never contacts prospects."""
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
                params={"q": payload.query.strip(), "count": min(20, payload.count * 2), "safesearch": "moderate"},
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

        # One result per hostname avoids presenting several pages from one site as separate leads.
        best_by_host: dict[str, dict] = {}
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = _public_https_url(item.get("url"))
            title = item.get("title")
            description = item.get("description")
            if not url or not isinstance(title, str) or not title.strip():
                continue
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower().rstrip(".")
            if host.startswith("www."):
                host = host[4:]
            if not host:
                continue
            clean_title = title.strip()[:300]
            clean_description = description.strip()[:1200] if isinstance(description, str) else ""
            score, reasons = _relevance(payload.query.strip(), clean_title, clean_description)
            candidate = {
                "title": clean_title,
                "url": url,
                "domain": host,
                "description": clean_description,
                "relevance_score": score,
                "relevance_reasons": reasons,
                "relevance_method": "query_term_overlap_v1",
                "evidence_type": "public_search_result",
                "requires_human_review": True,
            }
            previous = best_by_host.get(host)
            if previous is None or (score, len(clean_description)) > (
                previous["relevance_score"], len(previous["description"])
            ):
                best_by_host[host] = candidate

        results = sorted(
            best_by_host.values(),
            key=lambda item: (-item["relevance_score"], item["domain"], item["url"]),
        )[:payload.count]
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
        )
        return {
            "workspace_id": payload.workspace_id,
            "query": payload.query.strip(),
            "provider": "brave_search",
            "ranking": {
                "method": "query_term_overlap_v1",
                "description": "Lexical overlap between query, title and snippet; not a prediction of lead quality or conversion.",
            },
            "items": results,
            "count": len(results),
            "persisted_to_crm": False,
            "notice": "Search results and relevance scores are unverified hints. Review each source and establish business fit before saving or contacting anyone.",
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
