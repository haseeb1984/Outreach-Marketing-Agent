from __future__ import annotations

import asyncio

import httpx

from app.services.competitor_research import discover_competitor_candidates


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://api.search.brave.com/res/v1/web/search")

    def json(self):
        return self._body


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def get(self, url, *, params, headers):
        self.calls.append((url, params, headers))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def response(results):
    return FakeResponse({"web": {"results": results}})


def test_competitor_candidates_filter_own_domain_invalid_urls_and_dedupe_hosts():
    client = FakeClient([
        response([
            {"url": "https://www.client.example/products", "title": "Client products", "description": "Our own page"},
            {"url": "http://insecure.example", "title": "Insecure", "description": "Not HTTPS"},
            {"url": "https://competitor-one.example/page", "title": "CRM outreach platform", "description": "Business outreach and sales automation"},
        ]),
        response([
            {"url": "https://www.competitor-one.example/another-page", "title": "Business outreach tools", "description": "CRM tools"},
            {"url": "https://competitor-two.example/", "title": "Email automation", "description": "Email outreach tools"},
            {"url": "https://127.0.0.1/private", "title": "Local", "description": "Do not include"},
        ]),
    ])
    result = asyncio.run(discover_competitor_candidates(
        website_url="https://client.example",
        target_queries=["business outreach", "email automation"],
        api_key="test-api-key",
        client=client,
    ))

    assert result["status"] == "completed"
    assert result["count"] == 2
    assert {item["domain"] for item in result["items"]} == {
        "competitor-one.example", "competitor-two.example",
    }
    first = next(item for item in result["items"] if item["domain"] == "competitor-one.example")
    assert first["matched_queries"] == ["business outreach", "email automation"]
    assert first["requires_human_review"] is True
    assert first["competitor_status"] == "candidate_requires_human_review"
    assert len(client.calls) == 2
    assert all(call[2]["X-Subscription-Token"] == "test-api-key" for call in client.calls)


def test_competitor_candidates_are_unavailable_without_search_credentials():
    result = asyncio.run(discover_competitor_candidates(
        website_url="https://client.example",
        target_queries=["business outreach"],
        api_key=None,
        client=FakeClient([]),
    ))
    assert result["status"] == "unavailable"
    assert result["reason"] == "search_provider_not_configured"
    assert result["items"] == []


def test_competitor_candidates_fail_closed_for_invalid_client_domain():
    try:
        asyncio.run(discover_competitor_candidates(
            website_url="http://client.example",
            target_queries=["business outreach"],
            api_key="test-api-key",
            client=FakeClient([]),
        ))
    except ValueError as exc:
        assert str(exc) == "website_url_must_be_public_https"
    else:
        raise AssertionError("non-HTTPS client domain should be rejected")


def test_competitor_candidates_report_provider_failures_without_breaking_report():
    client = FakeClient([httpx.ConnectError("offline")])
    result = asyncio.run(discover_competitor_candidates(
        website_url="https://client.example",
        target_queries=["business outreach"],
        api_key="test-api-key",
        client=client,
    ))
    assert result["status"] == "unavailable"
    assert result["reason"] == "search_provider_unavailable"
