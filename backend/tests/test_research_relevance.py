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
        "https://[::1]/private",
        "https://[fe80::1]/private",
        "https://192.168.1.1/private",
        "https://2130706433/private",
        "https://example.com:8443/path",
        "javascript:alert(1)",
    ):
        assert _public_https_url(url) is None



def test_research_save_requires_explicit_human_review_and_rejects_extra_fields():
    import pytest
    from pydantic import ValidationError
    from app.api.research_routes import ResearchProspectSaveInput

    payload = {
        "workspace_id": "workspace-a",
        "name": "Example Prospect",
        "company": "Example Company",
        "website_url": "https://example.com",
        "evidence_url": "https://example.com/services",
        "fit_reason": "Reviewed source confirms relevant service.",
        "human_reviewed": True,
    }
    assert ResearchProspectSaveInput(**payload).human_reviewed is True
    with pytest.raises(ValidationError):
        ResearchProspectSaveInput(**{**payload, "human_reviewed": False, "send_now": True})


def test_research_save_persists_only_reviewed_prospect_for_authenticated_workspace(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import research_routes
    from app.main import app

    user_id = "00000000-0000-0000-0000-000000000001"
    saved = {}

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            assert kwargs == {"user_id": user_id, "workspace_id": "workspace-a", "minimum_role": "member"}
            return True

    class FakeProspectStore:
        async def create_prospect(self, **kwargs):
            saved.update(kwargs)
            return {"id": "prospect-1", "workspace_id": kwargs["workspace_id"]}

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": user_id}

    monkeypatch.setattr(research_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(research_routes, "_check_csrf", lambda request, session: None)
    payload = {
        "workspace_id": "workspace-a",
        "name": "Example Prospect",
        "company": "Example Company",
        "website_url": "https://example.com",
        "evidence_url": "https://example.com/services",
        "fit_reason": "Reviewed source confirms relevant service.",
        "verified_facts": ["Offers the target service."],
        "human_reviewed": True,
    }
    with TestClient(app) as client:
        app.state.auth_store = FakeAuthStore()
        app.state.prospect_store = FakeProspectStore()
        response = client.post("/api/v1/research/prospects/save", json=payload)

    assert response.status_code == 201
    assert saved["created_by"] == user_id
    assert saved["workspace_id"] == "workspace-a"
    assert saved["website_url"] == "https://example.com"
    assert saved["evidence_url"] == "https://example.com/services"
    assert saved["verified_facts"] == ["Offers the target service."]


def test_research_save_rejects_unreviewed_and_unsafe_urls_before_persistence(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import research_routes
    from app.main import app

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            return True

    class NeverProspectStore:
        async def create_prospect(self, **kwargs):
            raise AssertionError("invalid or unreviewed data must not reach persistence")

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": "00000000-0000-0000-0000-000000000001"}

    monkeypatch.setattr(research_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(research_routes, "_check_csrf", lambda request, session: None)
    payload = {
        "workspace_id": "workspace-a",
        "name": "Example Prospect",
        "company": "Example Company",
        "website_url": "https://example.com",
        "evidence_url": "https://example.com/services",
        "fit_reason": "Reviewed source confirms relevant service.",
        "human_reviewed": True,
    }
    with TestClient(app) as client:
        app.state.auth_store = FakeAuthStore()
        app.state.prospect_store = NeverProspectStore()
        unreviewed = client.post(
            "/api/v1/research/prospects/save",
            json={**payload, "human_reviewed": False},
        )
        unsafe_url = client.post(
            "/api/v1/research/prospects/save",
            json={**payload, "evidence_url": "https://127.0.0.1/internal"},
        )

    assert unreviewed.status_code == 422
    assert unreviewed.json()["detail"] == "human_review_required"
    assert unsafe_url.status_code == 422
    assert unsafe_url.json()["detail"] == "public_https_urls_required"


def test_research_save_rejects_cross_workspace_write(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import research_routes
    from app.main import app

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            return False

    class NeverProspectStore:
        async def create_prospect(self, **kwargs):
            raise AssertionError("cross-workspace writes must not reach persistence")

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": "00000000-0000-0000-0000-000000000001"}

    monkeypatch.setattr(research_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(research_routes, "_check_csrf", lambda request, session: None)
    payload = {
        "workspace_id": "workspace-other",
        "name": "Example Prospect",
        "company": "Example Company",
        "website_url": "https://example.com",
        "evidence_url": "https://example.com/services",
        "fit_reason": "Reviewed source confirms relevant service.",
        "human_reviewed": True,
    }
    with TestClient(app) as client:
        app.state.auth_store = FakeAuthStore()
        app.state.prospect_store = NeverProspectStore()
        response = client.post("/api/v1/research/prospects/save", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "workspace_not_found"


def test_research_save_schema_normalizes_text_and_rejects_blank_or_oversized_facts():
    import pytest
    from pydantic import ValidationError
    from app.api.research_routes import ResearchProspectSaveInput

    payload = {
        "workspace_id": "workspace-a",
        "name": "  Example Prospect  ",
        "company": " Example Company ",
        "website_url": "https://example.com",
        "evidence_url": "https://example.com/services",
        "fit_reason": " Reviewed source confirms relevant service. ",
        "verified_facts": [" Offers the target service. ", "Offers the target service."],
        "human_reviewed": True,
    }
    cleaned = ResearchProspectSaveInput(**payload)
    assert cleaned.name == "Example Prospect"
    assert cleaned.company == "Example Company"
    assert cleaned.verified_facts == ["Offers the target service."]
    with pytest.raises(ValidationError):
        ResearchProspectSaveInput(**{**payload, "name": "   "})
    with pytest.raises(ValidationError):
        ResearchProspectSaveInput(**{**payload, "verified_facts": ["x" * 1001]})
    with pytest.raises(ValidationError):
        ResearchProspectSaveInput(**{**payload, "verified_facts": ["   "]})


def test_research_save_maps_duplicate_evidence_to_conflict(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import research_routes
    from app.main import app

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            return True

    class UniqueViolationError(Exception):
        pass

    class DuplicateProspectStore:
        async def create_prospect(self, **kwargs):
            raise UniqueViolationError("duplicate evidence")

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": "00000000-0000-0000-0000-000000000001"}

    monkeypatch.setattr(research_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(research_routes, "_check_csrf", lambda request, session: None)
    payload = {
        "workspace_id": "workspace-a",
        "name": "Example Prospect",
        "company": "Example Company",
        "website_url": "https://example.com",
        "evidence_url": "https://example.com/services",
        "fit_reason": "Reviewed source confirms relevant service.",
        "human_reviewed": True,
    }
    with TestClient(app) as client:
        app.state.auth_store = FakeAuthStore()
        app.state.prospect_store = DuplicateProspectStore()
        response = client.post("/api/v1/research/prospects/save", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"] == "prospect_evidence_already_exists"


def test_research_save_hides_unexpected_persistence_errors(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import research_routes
    from app.main import app

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            return True

    class BrokenProspectStore:
        async def create_prospect(self, **kwargs):
            raise RuntimeError("private database details must not leak")

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": "00000000-0000-0000-0000-000000000001"}

    monkeypatch.setattr(research_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(research_routes, "_check_csrf", lambda request, session: None)
    payload = {
        "workspace_id": "workspace-a",
        "name": "Example Prospect",
        "company": "Example Company",
        "website_url": "https://example.com",
        "evidence_url": "https://example.com/services",
        "fit_reason": "Reviewed source confirms relevant service.",
        "human_reviewed": True,
    }
    with TestClient(app) as client:
        app.state.auth_store = FakeAuthStore()
        app.state.prospect_store = BrokenProspectStore()
        response = client.post("/api/v1/research/prospects/save", json=payload)

    assert response.status_code == 503
    assert response.json()["detail"] == "prospect_save_unavailable"
    assert "private database details" not in response.text


def test_search_route_consumes_reservation_on_unexpected_provider_processing_error():
    import inspect
    from app.api.research_routes import search_public_prospects

    source = inspect.getsource(search_public_prospects)
    generic_handler = source.rfind("except Exception:")
    assert generic_handler > source.index("async with httpx.AsyncClient")
    handler = source[generic_handler:]
    assert 'outcome="consumed"' in handler
    assert 'detail="search_provider_unavailable"' in handler
    assert "reservation_id=reservation_id" in handler
