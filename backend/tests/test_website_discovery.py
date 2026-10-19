import asyncio

from app.services import website_discovery
from app.services.website_fetch import FetchedPage


def page(url, status, content_type, body):
    return FetchedPage(
        requested_url=url,
        final_url=url,
        status_code=status,
        content_type=content_type,
        body=body,
    )


def test_discovery_uses_robots_and_sitemap_locations_as_crawl_seeds(monkeypatch):
    calls = []
    async def fake_fetch(url, **kwargs):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return page(url, 200, "text/plain", "User-agent: *\nDisallow: /private/\nSitemap: https://example.com/map.xml")
        if url.endswith("/map.xml"):
            return page(url, 200, "application/xml", """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://example.com/</loc></url>
              <url><loc>https://example.com/services</loc></url>
              <url><loc>https://other.example/escape</loc></url>
            </urlset>""")
        raise AssertionError(f"unexpected fetch: {url}")

    async def fake_crawl(start_url, **kwargs):
        assert kwargs["robots_txt"].startswith("User-agent")
        assert "https://example.com/services" in kwargs["seed_urls"]
        assert not any("other.example" in url for url in kwargs["seed_urls"])
        return {
            "start_url": start_url,
            "pages_crawled": 1,
            "pages": [],
            "aggregate_findings": [],
            "limitations": [],
        }

    monkeypatch.setattr(website_discovery, "fetch_text_document", fake_fetch)
    monkeypatch.setattr(website_discovery, "crawl_website", fake_crawl)
    result = asyncio.run(website_discovery.discover_and_crawl("https://example.com/"))
    assert result["crawl_skipped"] is False
    assert result["sitemap_seed_urls_discovered"] == 2
    assert result["crawl"]["pages_crawled"] == 1
    assert calls == ["https://example.com/robots.txt", "https://example.com/map.xml"]


def test_discovery_fails_closed_when_robots_cannot_be_retrieved(monkeypatch):
    async def fake_fetch(url, **kwargs):
        raise ValueError("Hostname resolves to a non-public IP address")

    async def forbidden_crawl(*args, **kwargs):
        raise AssertionError("crawl must not run when robots retrieval fails")

    monkeypatch.setattr(website_discovery, "fetch_text_document", fake_fetch)
    monkeypatch.setattr(website_discovery, "crawl_website", forbidden_crawl)
    result = asyncio.run(website_discovery.discover_and_crawl("https://example.com/"))
    assert result["crawl_skipped"] is True
    assert result["reason"] == "robots_txt_unavailable_fail_closed"


def test_discovery_allows_missing_robots_and_uses_default_sitemap(monkeypatch):
    calls = []
    async def fake_fetch(url, **kwargs):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return page(url, 404, "text/html", "not found")
        if url.endswith("/sitemap.xml"):
            return page(url, 404, "text/html", "not found")
        raise AssertionError(f"unexpected fetch: {url}")

    async def fake_crawl(start_url, **kwargs):
        assert kwargs["robots_txt"] is None
        return {"start_url": start_url, "pages_crawled": 0, "limitations": []}

    monkeypatch.setattr(website_discovery, "fetch_text_document", fake_fetch)
    monkeypatch.setattr(website_discovery, "crawl_website", fake_crawl)
    result = asyncio.run(website_discovery.discover_and_crawl("https://example.com/"))
    assert result["crawl_skipped"] is False
    assert result["robots"]["status"] == "not_found"
    assert calls == ["https://example.com/robots.txt", "https://example.com/sitemap.xml"]
