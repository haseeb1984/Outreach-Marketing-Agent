"""Evidence-led SEO strategy prioritization.

Ranks actions from supplied observations. It does not claim to know private
search-engine ranking weights and does not predict guaranteed rankings.
"""
from __future__ import annotations

from typing import Any


def build_seo_strategy(*, business_type: str, target_market: str, target_queries: list[str], site_findings: list[dict[str, Any]], competitor_gaps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Turn observed site issues and competitor gaps into a transparent action plan.

    Findings may include id, category, title, evidence_url, severity,
    affected_pages, business_relevance and recommended_action.
    Competitor gaps may include evidence_url, gap, business_relevance and
    recommended_action. This function does not fetch URLs or send data.
    """
    if not isinstance(business_type, str) or not business_type.strip() or len(business_type) > 200:
        raise ValueError("business_type must contain 1–200 characters")
    if not isinstance(target_market, str) or not target_market.strip() or len(target_market) > 200:
        raise ValueError("target_market must contain 1–200 characters")
    if (
        not isinstance(target_queries, list)
        or not target_queries
        or len(target_queries) > 100
        or any(
            not isinstance(query, str)
            or len(query) > 200
            or any(ord(char) < 32 and char not in "\\t" for char in query)
            for query in target_queries
        )
        or not any(query.strip() for query in target_queries)
    ):
        raise ValueError("target_queries must contain 1–100 valid queries of at most 200 characters")
    if not isinstance(site_findings, list):
        raise ValueError("site_findings must be a list")
    if competitor_gaps is not None and not isinstance(competitor_gaps, list):
        raise ValueError("competitor_gaps must be a list")

    actions: list[dict[str, Any]] = []
    for index, finding in enumerate(site_findings):
        if not isinstance(finding, dict):
            continue
        title = str(finding.get("title", "")).strip()
        evidence_url = str(finding.get("evidence_url", "")).strip()
        category = str(finding.get("category", "content")).strip().lower()
        if not title or not evidence_url:
            continue
        severity = _bounded_score(finding.get("severity", 2), default=2)
        relevance = _bounded_score(finding.get("business_relevance", 2), default=2)
        affected = _bounded_score(finding.get("affected_pages", 1), default=1, maximum=10000)
        # Transparent triage heuristic, not a search-engine ranking formula.
        score = round((severity * 0.45 + relevance * 0.35 + min(affected, 10) / 10 * 0.20) * 20, 1)
        actions.append({"id": str(finding.get("id") or f"site-{index + 1}"), "source": "site_observation", "category": category, "title": title, "evidence_url": evidence_url, "recommended_action": str(finding.get("recommended_action") or "Review this finding and define a verifiable correction."), "priority_score": score, "priority": _priority_label(score), "confidence": "evidence-backed", "verification": "Repeat the same check after an approved change and compare the recorded result."})

    for index, gap in enumerate(competitor_gaps or []):
        if not isinstance(gap, dict):
            continue
        title = str(gap.get("gap", "")).strip()
        evidence_url = str(gap.get("evidence_url", "")).strip()
        if not title or not evidence_url:
            continue
        relevance = _bounded_score(gap.get("business_relevance", 2), default=2)
        score = round(relevance * 20, 1)
        actions.append({"id": str(gap.get("id") or f"competitor-{index + 1}"), "source": "observed_competitor_gap", "category": "competitive_content", "title": title, "evidence_url": evidence_url, "recommended_action": str(gap.get("recommended_action") or "Validate user intent and create a more useful, differentiated answer if it serves the audience."), "priority_score": score, "priority": _priority_label(score), "confidence": "observed_gap_requires_validation", "verification": "Compare the target page against the cited competitor evidence and measure target-query outcomes over time."})

    actions.sort(key=lambda action: (-action["priority_score"], action["id"]))
    return {"business_context": {"business_type": business_type.strip(), "target_market": target_market.strip()}, "target_queries": list(dict.fromkeys(q.strip() for q in target_queries if q.strip())), "actions": actions, "method": {"name": "transparent_evidence_triage_v1", "score_range": "0-100", "score_meaning": "Internal prioritization heuristic only; not a Google/Bing ranking score or probability.", "ranking_guarantee": False}, "measurement_plan": ["Record baseline rankings and impressions for the target queries where authorized data is available.", "Record baseline organic clicks, conversions, and technical findings with timestamps.", "Implement only approved changes and preserve the evidence URL and change log.", "Re-run the same checks and compare query-level outcomes over a suitable period.", "Report observed results separately from correlation, estimates, and unverified hypotheses."], "limitations": ["Competitor pages reveal public signals, not competitors private analytics or exact search-engine weights.", "Search systems change and ranking outcomes depend on competition, intent, location, site history, and other factors.", "This output prioritizes supplied evidence; it does not crawl sites, change pages, or guarantee a ranking result."]}


def _bounded_score(value: Any, *, default: int, maximum: int = 5) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(maximum, score))


def _priority_label(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"
