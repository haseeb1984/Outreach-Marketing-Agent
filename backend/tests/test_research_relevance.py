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
    provider_call = source.index("async with httpx.AsyncClient")
    outer_handler = source.index("except Exception:", provider_call)
    handler = source[outer_handler:]
    assert 'outcome="consumed"' in handler
    assert 'detail="search_provider_unavailable"' in handler
    assert "reservation_id=reservation_id" in handler


def test_influencer_profile_normalization_accepts_only_public_profile_shapes():
    from app.api.research_routes import _public_influencer_profile

    assert _public_influencer_profile("https://www.instagram.com/creator.name/?igsh=abc") == (
        "https://instagram.com/creator.name", "instagram"
    )
    assert _public_influencer_profile("https://www.tiktok.com/@creator") == (
        "https://tiktok.com/@creator", "tiktok"
    )
    assert _public_influencer_profile("https://www.youtube.com/@creator/videos") is None
    assert _public_influencer_profile("https://www.youtube.com/@creator") == (
        "https://youtube.com/@creator", "youtube"
    )
    assert _public_influencer_profile("https://www.linkedin.com/in/creator-profile/") == (
        "https://linkedin.com/in/creator-profile", "linkedin"
    )
    assert _public_influencer_profile("https://x.com/creator/status/123") is None
    assert _public_influencer_profile("https://instagram.com/explore") is None
    assert _public_influencer_profile("https://example.com/creator") is None


def test_influencer_search_uses_workspace_quota_and_returns_only_reviewable_profile_candidates(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import research_routes
    from app.main import app

    user_id = "00000000-0000-0000-0000-000000000001"
    finished = []

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            return kwargs == {
                "user_id": user_id, "workspace_id": "workspace-a", "minimum_role": "member"
            }

    class FakeSubscriptions:
        async def reserve_usage(self, **kwargs):
            assert kwargs["feature"] == "prospect_research"
            assert kwargs["idempotency_key"] == "influencer-research:test-key-123"
            return {"allowed": True, "reservation_id": "reservation-1", "status": "reserved"}

        async def finish_reservation(self, **kwargs):
            finished.append(kwargs)
            return True

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"web": {"results": [
                {"url": "https://www.instagram.com/creator.one/?ref=search",
                 "title": "Creator One | Karachi food creator",
                 "description": "Food reviews and restaurant videos in Karachi"},
                {"url": "https://instagram.com/creator.one/",
                 "title": "Creator One | Karachi food creator",
                 "description": "Food reviews and restaurant videos in Karachi"},
                {"url": "https://www.instagram.com/p/ABC123/",
                 "title": "Karachi food creator post", "description": "Post URL, not a profile"},
                {"url": "https://www.youtube.com/@foodcreator",
                 "title": "Food Creator", "description": "Karachi restaurant reviews"},
                {"url": "https://example.com/creator",
                 "title": "Karachi food influencer", "description": "Not a supported creator profile"},
            ]}}

    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, *, params, headers):
            assert "site:instagram.com" in params["q"]
            assert "site:youtube.com" in params["q"]
            assert headers["X-Subscription-Token"] == "test-search-key"
            return FakeResponse()

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": user_id}

    monkeypatch.setattr(research_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(research_routes, "_check_csrf", lambda request, session: None)
    monkeypatch.setattr(research_routes, "settings", type("Settings", (), {"brave_search_api_key": "test-search-key"})())
    monkeypatch.setattr(research_routes.httpx, "AsyncClient", FakeHttpClient)

    with TestClient(app) as client:
        app.state.auth_store = FakeAuthStore()
        app.state.subscription_store = FakeSubscriptions()
        response = client.post("/api/v1/research/influencers/search", json={
            "workspace_id": "workspace-a",
            "query": "Karachi food creator",
            "platforms": ["instagram", "youtube"],
            "count": 10,
            "idempotency_key": "test-key-123",
        })

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert {item["platform"] for item in body["items"]} == {"instagram", "youtube"}
    assert len({item["profile_url"] for item in body["items"]}) == 2
    assert all(item["requires_human_review"] for item in body["items"])
    assert all(item["audience_metrics"] is None for item in body["items"])
    assert "engagement rate" in body["unavailable_metrics"]
    assert body["persisted_to_crm"] is False
    assert len(finished) == 1
    assert finished[0]["outcome"] == "consumed"


def test_influencer_profile_normalization_rejects_nested_content_paths():
    from app.api.research_routes import _public_influencer_profile

    assert _public_influencer_profile("https://www.linkedin.com/in/creator/posts/123") is None
    assert _public_influencer_profile("https://www.youtube.com/channel/UC123/videos") is None
    assert _public_influencer_profile("https://www.youtube.com/c/creator/community") is None
    assert _public_influencer_profile("https://www.linkedin.com/in/creator-profile") == (
        "https://linkedin.com/in/creator-profile", "linkedin"
    )
    assert _public_influencer_profile("https://www.youtube.com/channel/UC123") == (
        "https://youtube.com/channel/UC123", "youtube"
    )


def test_influencer_search_quota_denial_does_not_call_provider(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import research_routes
    from app.main import app

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            return True

    class DeniedSubscriptions:
        async def reserve_usage(self, **kwargs):
            return {"allowed": False, "reason": "quota_exhausted"}

    class NeverHttpClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("provider must not be called when quota is denied")

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": "00000000-0000-0000-0000-000000000001"}

    monkeypatch.setattr(research_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(research_routes, "_check_csrf", lambda request, session: None)
    monkeypatch.setattr(research_routes, "settings", type("Settings", (), {"brave_search_api_key": "test-search-key"})())
    monkeypatch.setattr(research_routes.httpx, "AsyncClient", NeverHttpClient)

    with TestClient(app) as client:
        app.state.auth_store = FakeAuthStore()
        app.state.subscription_store = DeniedSubscriptions()
        response = client.post("/api/v1/research/influencers/search", json={
            "workspace_id": "workspace-a",
            "query": "Karachi food creators",
            "platforms": ["instagram"],
            "idempotency_key": "quota-key-123",
        })

    assert response.status_code == 429
    assert response.json()["detail"] == "quota_exhausted"


def test_influencer_search_fails_closed_when_search_provider_is_not_configured(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import research_routes
    from app.main import app

    class FakeAuthStore:
        async def authorize_workspace(self, **kwargs):
            return True

    class NeverSubscriptions:
        async def reserve_usage(self, **kwargs):
            raise AssertionError("quota must not be reserved without a configured provider")

    async def fake_authenticated(request):
        return FakeAuthStore(), "session-token", {"user_id": "00000000-0000-0000-0000-000000000001"}

    monkeypatch.setattr(research_routes, "_authenticated", fake_authenticated)
    monkeypatch.setattr(research_routes, "_check_csrf", lambda request, session: None)
    monkeypatch.setattr(research_routes, "settings", type("Settings", (), {"brave_search_api_key": " "})())

    with TestClient(app) as client:
        app.state.auth_store = FakeAuthStore()
        app.state.subscription_store = NeverSubscriptions()
        response = client.post("/api/v1/research/influencers/search", json={
            "workspace_id": "workspace-a",
            "query": "Karachi food creators",
            "platforms": ["instagram"],
            "idempotency_key": "no-provider-123",
        })

    assert response.status_code == 503
    assert response.json()["detail"] == "search_provider_not_configured"
