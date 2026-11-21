"""Quota-controlled, evidence-ranked public-web prospect discovery.

Search results are suggestions only: they are not automatically added to the CRM and
must be reviewed by a person. Relevance scores are transparent text-match heuristics,
not lead-conversion predictions. The provider credential is read from server environment.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.auth_routes import _authenticated, _check_csrf
from app.core.config import settings

router = APIRouter(prefix="/api/v1/research", tags=["prospect research"])


class ProspectSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=3, max_length=400)
    count: int = Field(default=10, ge=1, le=20)
    idempotency_key: str = Field(min_length=8, max_length=180, pattern=r"^[A-Za-z0-9._:-]+$")




class ResearchProspectSaveInput(BaseModel):
    """Explicit human-reviewed selection to persist a research result to the CRM."""
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=240)
    website_url: str = Field(min_length=8, max_length=2048)
    evidence_url: str = Field(min_length=8, max_length=2048)
    fit_reason: str = Field(min_length=1, max_length=2000)
    verified_facts: list[str] = Field(default_factory=list, max_length=30)
    human_reviewed: bool

    @field_validator("name", "company", "fit_reason")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must_not_be_blank")
        return cleaned

    @field_validator("verified_facts")
    @classmethod
    def normalize_verified_facts(cls, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            fact = value.strip()
            if not fact:
                raise ValueError("verified_facts_must_not_be_blank")
            if len(fact) > 1000:
                raise ValueError("verified_fact_too_long")
            if fact not in cleaned:
                cleaned.append(fact)
        return cleaned


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
        # Reject IP literals (including IPv6) as prospect evidence; do not
        # rely only on dotted-decimal IPv4 string matching.
        try:
            ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            pass
        else:
            return None
        if not host or "." not in host or host.replace(".", "").isdigit():
            return None
        return value
    except ValueError:
        return None


_SEARCH_STOP_WORDS = {
    "about", "and", "are", "for", "from", "how", "into", "its", "our", "the",
    "their", "this", "that", "with", "you", "your", "who", "what", "where",
}


def _search_terms(value: str) -> set[str]:
    """Normalize words while ignoring short and common low-information tokens."""
    return {
        term for term in re.findall(r"[a-z0-9]+", value.lower())
        if len(term) >= 3 and term not in _SEARCH_STOP_WORDS
    }


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
    except Exception:
        # Unexpected failures after the provider call may have incurred billable usage.
        # Finalize the reservation rather than leaving it indefinitely reserved or
        # allowing an idempotent retry to repeat the paid search.
        try:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="search_provider_unavailable") from None


class InfluencerSearchInput(BaseModel):
    """Find public creator-profile candidates; never estimates audience or engagement."""
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=3, max_length=400)
    platforms: list[str] = Field(default_factory=lambda: ["instagram", "tiktok", "youtube", "linkedin", "x"], min_length=1, max_length=5)
    count: int = Field(default=10, ge=1, le=20)
    idempotency_key: str = Field(min_length=8, max_length=180, pattern=r"^[A-Za-z0-9._:-]+$")

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, values: list[str]) -> list[str]:
        allowed = {"instagram", "tiktok", "youtube", "linkedin", "x"}
        normalized = list(dict.fromkeys(value.strip().lower() for value in values))
        if not normalized or any(value not in allowed for value in normalized):
            raise ValueError("unsupported_influencer_platform")
        return normalized

    @field_validator("workspace_id", "query")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value_must_not_be_blank")
        return normalized


_INFLUENCER_HOSTS = {
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "linkedin.com": "linkedin",
    "x.com": "x",
    "twitter.com": "x",
}


def _public_influencer_profile(value: object) -> tuple[str, str] | None:
    """Return a canonical public creator profile URL and platform, excluding content/search URLs."""
    safe = _public_https_url(value)
    if safe is None:
        return None
    parsed = urlsplit(safe)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    platform = _INFLUENCER_HOSTS.get(host)
    if platform is None:
        return None
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return None
    first = segments[0].lower()
    reserved = {
        "instagram": {"p", "reel", "reels", "explore", "stories", "direct", "accounts"},
        "tiktok": {"discover", "tag", "music", "search", "foryou", "upload"},
        "youtube": {"watch", "shorts", "playlist", "results", "feed", "gaming"},
        "linkedin": {"company", "school", "jobs", "feed", "posts", "search"},
        "x": {"home", "explore", "search", "i", "intent", "share", "notifications", "messages"},
    }
    if first in reserved[platform]:
        return None
    if platform == "tiktok" and not segments[0].startswith("@"):
        return None
    if platform == "youtube" and not (
        segments[0].startswith("@") or first in {"channel", "c", "user"}
    ):
        return None
    if platform == "linkedin" and first != "in":
        return None
    if platform == "linkedin" and (first != "in" or len(segments) != 2):
        return None
    if platform == "youtube" and first in {"channel", "c", "user"} and len(segments) != 2:
        return None
    if platform in {"instagram", "x"} and len(segments) != 1:
        return None
    if platform == "tiktok" and len(segments) != 1:
        return None
    if platform == "youtube" and first.startswith("@") and len(segments) != 1:
        return None
    canonical_path = "/" + "/".join(segments)
    return f"https://{host}{canonical_path}", platform


@router.post("/influencers/search")
async def search_public_influencers(payload: InfluencerSearchInput, request: Request) -> dict:
    """Discover public creator-profile candidates with explainable relevance, not influence scores."""
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

    site_domains = {
        "instagram": "instagram.com", "tiktok": "tiktok.com",
        "youtube": "youtube.com", "linkedin": "linkedin.com", "x": "x.com",
    }
    site_filter = " OR ".join("site:" + site_domains[name] for name in payload.platforms)
    search_query = f'({payload.query.strip()}) (creator OR influencer OR "content creator") ({site_filter})'
    try:
        reservation = await subscriptions.reserve_usage(
            workspace_id=payload.workspace_id,
            feature="prospect_research",
            idempotency_key="influencer-research:" + payload.idempotency_key,
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
                params={"q": search_query, "count": min(20, payload.count * 3), "safesearch": "moderate"},
                headers={"Accept": "application/json", "X-Subscription-Token": settings.brave_search_api_key},
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

        by_profile: dict[str, dict] = {}
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            profile = _public_influencer_profile(item.get("url"))
            title, description = item.get("title"), item.get("description")
            if profile is None or not isinstance(title, str) or not title.strip():
                continue
            profile_url, platform = profile
            if platform not in payload.platforms:
                continue
            clean_title = title.strip()[:300]
            clean_description = description.strip()[:1200] if isinstance(description, str) else ""
            score, reasons = _relevance(payload.query.strip(), clean_title, clean_description)
            candidate = {
                "profile_url": profile_url,
                "platform": platform,
                "title": clean_title,
                "description": clean_description,
                "relevance_score": score,
                "relevance_reasons": reasons,
                "relevance_method": "query_term_overlap_v1",
                "evidence_type": "public_search_result",
                "requires_human_review": True,
                "audience_metrics": None,
                "audience_metrics_status": "not_available_from_search_results",
            }
            previous = by_profile.get(profile_url)
            if previous is None or (score, len(clean_description)) > (
                previous["relevance_score"], len(previous["description"])
            ):
                by_profile[profile_url] = candidate

        items = sorted(
            by_profile.values(),
            key=lambda item: (-item["relevance_score"], item["platform"], item["profile_url"]),
        )[:payload.count]
        await subscriptions.finish_reservation(
            workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
        )
        return {
            "workspace_id": payload.workspace_id,
            "query": payload.query.strip(),
            "platforms": payload.platforms,
            "provider": "brave_search",
            "quota_feature": "prospect_research",
            "ranking": {
                "method": "query_term_overlap_v1",
                "description": "Matches query terms against public search-result titles and snippets; this is topical relevance, not creator quality, reach, engagement or conversion likelihood.",
            },
            "items": items,
            "count": len(items),
            "persisted_to_crm": False,
            "unavailable_metrics": ["followers", "average views", "engagement rate", "audience demographics", "verified conversions", "revenue", "ROI"],
            "notice": "Profiles are public-search candidates, not endorsed creators. Review identity, audience fit, current metrics and commercial terms independently before contacting or saving anyone.",
        }
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        try:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="search_provider_unavailable") from None
    except Exception:
        try:
            await subscriptions.finish_reservation(
                workspace_id=payload.workspace_id, reservation_id=reservation_id, outcome="consumed"
            )
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="search_provider_unavailable") from None


@router.post("/prospects/save", status_code=201)
async def save_researched_prospect(payload: ResearchProspectSaveInput, request: Request) -> dict:
    """Save one reviewed search result; discovery results are never auto-imported."""
    _, _, session = await _authenticated(request)
    _check_csrf(request, session)
    auth_store = getattr(request.app.state, "auth_store", None)
    if auth_store is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not await auth_store.authorize_workspace(
        user_id=session["user_id"], workspace_id=payload.workspace_id, minimum_role="member"
    ):
        raise HTTPException(status_code=404, detail="workspace_not_found")
    if payload.human_reviewed is not True:
        raise HTTPException(status_code=422, detail="human_review_required")
    website_url = _public_https_url(payload.website_url)
    evidence_url = _public_https_url(payload.evidence_url)
    if website_url is None or evidence_url is None:
        raise HTTPException(status_code=422, detail="public_https_urls_required")
    store = getattr(request.app.state, "prospect_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="prospect_service_not_configured")
    try:
        return await store.create_prospect(
            workspace_id=payload.workspace_id, created_by=session["user_id"],
            name=payload.name, company=payload.company, website_url=website_url,
            evidence_url=evidence_url, fit_reason=payload.fit_reason,
            verified_facts=payload.verified_facts,
        )
    except Exception as exc:
        if type(exc).__name__ == "UniqueViolationError":
            raise HTTPException(status_code=409, detail="prospect_evidence_already_exists") from None
        raise HTTPException(status_code=503, detail="prospect_save_unavailable") from None
