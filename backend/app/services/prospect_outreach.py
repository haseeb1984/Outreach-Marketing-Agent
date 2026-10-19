"""Evidence-grounded prospect fit and outreach draft generation.

Draft-only utilities: no message is sent, no contact details are discovered, and
unsupported business claims are not added to the generated copy.
"""
from __future__ import annotations

from typing import Any


def score_prospect_fit(*, client_business: str, target_customer_profile: str, prospect: dict[str, Any]) -> dict[str, Any]:
    """Score a prospect using explicit, source-backed fit signals supplied by research.

    prospect fields: name, evidence_url, observed_fit_signals (list of strings),
    verified_facts (list of strings), and optional disqualifiers (list of strings).
    The score is a transparent internal triage heuristic, not a conversion forecast.
    """
    if not client_business.strip() or not target_customer_profile.strip():
        raise ValueError("client_business and target_customer_profile are required")
    name = str(prospect.get("name", "")).strip()
    evidence_url = str(prospect.get("evidence_url", "")).strip()
    if not name or not evidence_url:
        raise ValueError("prospect name and evidence_url are required")
    signals = _clean_list(prospect.get("observed_fit_signals", []))
    facts = _clean_list(prospect.get("verified_facts", []))
    disqualifiers = _clean_list(prospect.get("disqualifiers", []))
    # Each explicitly observed fit signal adds 20 points; disqualifiers cap the score at 20.
    score = min(100, len(signals) * 20)
    if disqualifiers:
        score = min(score, 20)
    return {
        "prospect_name": name,
        "evidence_url": evidence_url,
        "client_business": client_business.strip(),
        "target_customer_profile": target_customer_profile.strip(),
        "observed_fit_signals": signals,
        "verified_facts": facts,
        "disqualifiers": disqualifiers,
        "fit_score": score,
        "fit_band": "high" if score >= 60 and not disqualifiers else "medium" if score >= 40 and not disqualifiers else "low",
        "score_note": "Internal evidence-count heuristic only; not a probability of reply, sale, or conversion.",
        "review_required": True,
    }


def draft_outreach(*, channel: str, client_business: str, client_offer: str, prospect_name: str, prospect_evidence_url: str, verified_relevance: str, verified_facts: list[str], call_to_action: str, whatsapp_opt_in_confirmed: bool = False) -> dict[str, Any]:
    """Create a short draft from verified inputs; never send it.

    WhatsApp drafts are refused unless the caller explicitly confirms documented
    opt-in. The caller remains responsible for validating applicable law and
    provider policy before any later sending integration is used.
    """
    channel = channel.strip().lower()
    if channel not in {"email", "whatsapp"}:
        raise ValueError("channel must be email or whatsapp")
    required = {"client_business": client_business, "client_offer": client_offer, "prospect_name": prospect_name, "prospect_evidence_url": prospect_evidence_url, "verified_relevance": verified_relevance, "call_to_action": call_to_action}
    missing = [key for key, value in required.items() if not str(value).strip()]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))
    facts = _clean_list(verified_facts)
    if not facts:
        raise ValueError("at least one verified fact is required")
    if channel == "whatsapp" and not whatsapp_opt_in_confirmed:
        raise ValueError("WhatsApp outreach draft requires confirmed documented opt-in")
    relevance = verified_relevance.strip()
    fact_sentence = " ".join(facts[:2])
    if channel == "email":
        subject = f"Idea for {prospect_name.strip()}"
        body = f"Hi {prospect_name.strip()},\n\nI’m reaching out from {client_business.strip()}. {relevance} I noticed: {fact_sentence}\n\nWe help with {client_offer.strip()}. Would {call_to_action.strip()} be useful to discuss?\n\nIf this is not relevant, please let me know and I will not follow up."
    else:
        subject = None
        body = f"Hi {prospect_name.strip()}, this is a message from {client_business.strip()}. {relevance} I noticed: {fact_sentence} We help with {client_offer.strip()}. Would {call_to_action.strip()} be useful? If you prefer not to receive messages, let me know and I will stop."
    return {"channel": channel, "subject": subject, "body": body, "source_evidence_url": prospect_evidence_url.strip(), "verified_facts_used": facts[:2], "status": "draft_requires_human_review", "sent": False, "personalization_basis": "Only the supplied verified facts and relevance statement were used."}


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
