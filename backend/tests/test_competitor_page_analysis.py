from __future__ import annotations

import asyncio

import httpx

from app.services.competitor_page_analysis import analyze_competitor_pages


async def _public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


def _run(handler, *, client_pages=None):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await analyze_competitor_pages(
                candidates=[{
                    "domain": "competitor.example",
                    "url": "https://competitor.example/products/automation",
                }],
                target_queries=["email outreach automation"],
                client_pages=client_pages or [{
                    "url": "https://client.example/",
                    "title": "Contact us",
                    "meta_descriptions": [],
                    "headings": {"h1": ["Contact"]},
                }],
                client=client,
                resolver=_public_resolver,
            )
    return asyncio.run(execute())


def test_competitor_page_comparison_returns_evidence_backed_potential_gap():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404, headers={"content-type": "text/plain"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>Email outreach automation platform</title>"
                "<meta name='description' content='Email outreach automation for sales teams'></head>"
                "<body><h1>Email outreach automation</h1>"
                "<h2>Automate prospect follow-up</h2></body></html>"
            ),
        )

    result = _run(handler)
    assert result["status"] == "completed"
    assert result["pages_analyzed"] == 1
    assert result["items"][0]["evidence_type"] == "fetched_public_page_metadata_and_headings"
    assert result["potential_gaps"][0]["classification"] == "potential_content_coverage_gap"
    assert result["potential_gaps"][0]["competitor_evidence_url"].startswith("https://competitor.example/")
    assert result["potential_gaps"][0]["client_evidence_urls"] == ["https://client.example/"]
    assert result["potential_gaps"][0]["requires_human_review"] is True


def test_competitor_page_comparison_respects_robots_disallow():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="User-agent: *\nDisallow: /products",
            )
        raise AssertionError("disallowed page must not be fetched")

    result = _run(handler)
    assert result["status"] == "unavailable"
    assert result["items"][0]["status"] == "skipped_robots"
    assert result["potential_gaps"] == []


def test_competitor_page_comparison_does_not_flag_query_already_covered_by_client():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404, headers={"content-type": "text/plain"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><head><title>Email outreach automation</title></head>"
                 "<body><h1>Email outreach automation</h1></body></html>",
        )

    result = _run(handler, client_pages=[{
        "url": "https://client.example/services",
        "title": "Email outreach automation",
        "meta_descriptions": ["Email outreach automation for businesses"],
        "headings": {"h1": ["Email outreach automation"]},
    }])
    assert result["status"] == "completed"
    assert result["potential_gaps"] == []
