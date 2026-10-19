import asyncio

from app.services import website_crawler
from app.services.website_fetch import FetchedPage


def test_crawler_visits_same_host_pages_with_bounds_and_aggregates_findings(monkeypatch):
    documents = {
        "https://example.com/": '<html><head><title>Home</title><meta name="viewport" content="width=device-width"></head><body><h1>Home</h1><a href="/about">About</a><a href="https://other.example/page">Offsite</a><a href="/#section">Fragment</a></body></html>',
        "https://example.com/about": '<html><head><title>About</title></head><body><h1>About</h1><a href="/">Home</a><img src="/image.png"></body></html>',
    }
    seen = []

    async def fake_fetch(url, **kwargs):
        seen.append((url, kwargs.get("allowed_hosts")))
        return FetchedPage(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=documents[url],
        )

    monkeypatch.setattr(website_crawler, "fetch_html", fake_fetch)
    report = asyncio.run(website_crawler.crawl_website("https://example.com/", max_pages=10, max_depth=2))

    assert report["pages_crawled"] == 2
    assert [page["title"] for page in report["pages"]] == ["Home", "About"]
    assert all(hosts == {"example.com"} for _, hosts in seen)
    assert any(item["code"] == "missing_meta_description" and item["occurrences"] == 2 for item in report["aggregate_findings"])
    assert all("other.example" not in url for url, _ in seen)


def test_crawler_respects_page_and_depth_limits(monkeypatch):
    async def fake_fetch(url, **kwargs):
        return FetchedPage(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            body=f'<html><head><title>{url}</title></head><body><h1>Page</h1><a href="/next">Next</a></body></html>',
        )

    monkeypatch.setattr(website_crawler, "fetch_html", fake_fetch)
    report = asyncio.run(website_crawler.crawl_website("https://example.com/", max_pages=1, max_depth=5))
    assert report["pages_crawled"] == 1

    report = asyncio.run(website_crawler.crawl_website("https://example.com/", max_pages=10, max_depth=0))
    assert report["pages_crawled"] == 1


def test_crawler_rejects_excessive_limits():
    for kwargs in ({"max_pages": 101}, {"max_pages": 0}, {"max_depth": 6}, {"max_depth": -1}):
        try:
            asyncio.run(website_crawler.crawl_website("https://example.com/", **kwargs))
        except ValueError:
            pass
        else:
            raise AssertionError("invalid crawl limit should be rejected")
