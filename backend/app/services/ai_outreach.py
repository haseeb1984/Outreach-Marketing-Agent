"""Optional OpenAI-compatible, evidence-grounded outreach copy generation."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

import httpx


class AIOutreachUnavailable(RuntimeError):
    pass


async def generate_ai_outreach(*, api_key: str, base_url: str, model: str,
                               channel: str, call_to_action: str,
                               context: dict[str, Any]) -> dict[str, str]:
    """Generate copy from verified workspace facts; never send or discover contacts."""
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise AIOutreachUnavailable("ai_provider_configuration_invalid")
    facts = context.get("verified_facts")
    if not isinstance(facts, list) or not facts:
        raise ValueError("at least one verified fact is required")
    if channel not in {"email", "whatsapp"}:
        raise ValueError("invalid_channel")
    payload = {
        "business": context["client_business"],
        "offer": context["client_offer"],
        "prospect_name": context["prospect_name"],
        "verified_relevance": context["fit_reason"],
        "verified_facts": facts[:8],
        "source_evidence_url": context["evidence_url"],
        "call_to_action": call_to_action,
        "channel": channel,
    }
    prompt = (
        "Write concise, natural, individually personalized B2B outreach. Use ONLY "
        "the supplied business details and verified facts. Do not infer metrics, "
        "customers, outcomes, personal details, or claims. Do not claim research "
        "beyond the supplied evidence. Keep the CTA low-friction. Avoid deceptive "
        "urgency. For email return a useful subject and body. For WhatsApp return "
        "a brief body and empty subject. Include a polite opt-out sentence. "
        "Return JSON only with exactly keys subject and body.\nINPUT:\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=5.0)) as client:
            response = await client.post(
                base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "You are a careful B2B copywriter. Evidence only; never invent facts."},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            result = response.json()
            draft = json.loads(result["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        raise AIOutreachUnavailable("ai_provider_unavailable") from None
    subject = draft.get("subject")
    body = draft.get("body")
    if not isinstance(body, str) or not body.strip() or len(body) > 10000:
        raise AIOutreachUnavailable("ai_response_invalid")
    if channel == "email" and (not isinstance(subject, str) or not subject.strip() or len(subject) > 300):
        raise AIOutreachUnavailable("ai_response_invalid")
    return {"subject": subject.strip() if isinstance(subject, str) else "", "body": body.strip()}
