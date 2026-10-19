import pytest

from app.services.prospect_outreach import draft_outreach, score_prospect_fit


def test_prospect_fit_is_traceable_and_disqualifiers_limit_score():
    result = score_prospect_fit(client_business="SEO agency", target_customer_profile="local retailers", prospect={"name": "Example Shop", "evidence_url": "https://example.com/about", "observed_fit_signals": ["has local storefront", "site has service pages", "public business contact page"], "verified_facts": ["Operates two retail locations"], "disqualifiers": ["Existing agency contract shown in source"]})
    assert result["fit_score"] == 20
    assert result["fit_band"] == "low"
    assert result["review_required"] is True
    assert result["evidence_url"] == "https://example.com/about"


def test_email_draft_uses_only_supplied_facts_and_is_never_sent():
    result = draft_outreach(channel="email", client_business="Acme SEO", client_offer="technical SEO audits", prospect_name="Example Shop", prospect_evidence_url="https://example.com/about", verified_relevance="Your public site lists two store locations.", verified_facts=["The site lists two store locations."], call_to_action="a brief introductory call")
    assert "two store locations" in result["body"]
    assert result["status"] == "draft_requires_human_review"
    assert result["sent"] is False
    assert result["source_evidence_url"] == "https://example.com/about"


def test_whatsapp_draft_requires_confirmed_opt_in():
    kwargs = {"channel": "whatsapp", "client_business": "Acme", "client_offer": "SEO services", "prospect_name": "Example", "prospect_evidence_url": "https://example.com", "verified_relevance": "You publish a local store directory.", "verified_facts": ["A directory is available on the site."], "call_to_action": "a short call"}
    with pytest.raises(ValueError, match="opt-in"):
        draft_outreach(**kwargs)
    result = draft_outreach(**kwargs, whatsapp_opt_in_confirmed=True)
    assert result["channel"] == "whatsapp"
    assert result["sent"] is False
