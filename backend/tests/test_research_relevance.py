from app.api.research_routes import _public_https_url, _relevance, _search_terms


def test_relevance_score_is_bounded_and_explains_query_matches():
    score, reasons = _relevance(
        "Karachi dental clinic",
        "Karachi dental clinic services",
        "Family dentistry and emergency dental care",
    )

    assert 0 <= score <= 100
    assert score > 0
    assert reasons[0] == "Title matches: clinic, dental, karachi"
    assert "Description matches: dental" in reasons


def test_relevance_prefers_title_matches_over_snippet_only_matches():
    title_match, _ = _relevance("agency outreach software", "Agency outreach software", "")
    snippet_match, _ = _relevance("agency outreach software", "Helpful resources", "Agency outreach software")
    assert title_match > snippet_match


def test_relevance_is_case_insensitive_and_does_not_reward_repeated_terms():
    first, _ = _relevance("SEO audit agency", "SEO audit agency", "SEO SEO SEO")
    second, _ = _relevance("seo audit agency", "seo audit agency", "seo seo seo")
    assert first == second
    assert first <= 100


def test_search_terms_ignore_short_words_and_non_word_punctuation():
    assert _search_terms("SEO for B2B-agencies!") == {"seo", "b2b", "agencies"}


def test_public_search_result_urls_reject_non_public_or_unsafe_shapes():
    assert _public_https_url("https://example.com/services") == "https://example.com/services"
    for url in (
        "http://example.com",
        "https://user:pass@example.com",
        "https://localhost/admin",
        "https://app.internal",
        "https://127.0.0.1/private",
        "https://example.com:8443/path",
        "javascript:alert(1)",
    ):
        assert _public_https_url(url) is None
