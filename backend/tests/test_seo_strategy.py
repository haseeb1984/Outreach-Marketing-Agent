import pytest

from app.services.seo_strategy import build_seo_strategy


def test_strategy_prioritizes_evidence_backed_technical_issue():
    result = build_seo_strategy(business_type="local dental clinic", target_market="Karachi", target_queries=["dentist Karachi", "emergency dentist Karachi"], site_findings=[{"id": "indexability", "category": "indexability", "title": "Important service page is marked noindex", "evidence_url": "https://client.example/services", "severity": 5, "business_relevance": 5, "affected_pages": 3, "recommended_action": "Confirm intent, then remove noindex only if the page should be indexed."}, {"title": "Unverified claim", "severity": 5}], competitor_gaps=[{"gap": "Competitor answers emergency-hours intent with a dedicated page", "evidence_url": "https://competitor.example/emergency", "business_relevance": 4}])
    assert len(result["actions"]) == 2
    assert result["actions"][0]["id"] == "indexability"
    assert result["actions"][0]["priority"] == "high"
    assert result["actions"][0]["evidence_url"].startswith("https://")
    assert result["method"]["ranking_guarantee"] is False
    assert result["measurement_plan"]


def test_strategy_deduplicates_queries_and_skips_evidence_free_gaps():
    result = build_seo_strategy(business_type="B2B software", target_market="Global", target_queries=["crm for agencies", "crm for agencies", " "], site_findings=[], competitor_gaps=[{"gap": "Possibly missing comparison page"}])
    assert result["target_queries"] == ["crm for agencies"]
    assert result["actions"] == []


@pytest.mark.parametrize("kwargs", [{"business_type": "", "target_market": "Global", "target_queries": ["x"]}, {"business_type": "SaaS", "target_market": "", "target_queries": ["x"]}, {"business_type": "SaaS", "target_market": "Global", "target_queries": [" "]}])
def test_strategy_requires_business_context_and_target_query(kwargs):
    with pytest.raises(ValueError):
        build_seo_strategy(**kwargs, site_findings=[])


def test_competitor_page_gap_merges_into_prioritized_actions_with_evidence():
    from app.services.seo_strategy import merge_competitor_content_gaps

    base = build_seo_strategy(
        business_type="B2B software",
        target_market="Global",
        target_queries=["email outreach automation"],
        site_findings=[],
    )
    result = merge_competitor_content_gaps(base, [{
        "query": "email outreach automation",
        "classification": "potential_content_coverage_gap",
        "priority_score": 82.5,
        "confidence": "medium",
        "competitor_evidence_url": "https://competitor.example/email-automation",
        "requires_human_review": True,
    }])
    assert len(result["actions"]) == 1
    action = result["actions"][0]
    assert action["source"] == "observed_competitor_gap"
    assert action["priority"] == "high"
    assert action["evidence_url"] == "https://competitor.example/email-automation"
    assert action["confidence"] == "medium_requires_validation"
    assert action["verification"]
