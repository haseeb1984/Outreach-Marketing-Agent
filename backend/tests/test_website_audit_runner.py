import asyncio

from app.services import website_audit_runner
from app.services.website_fetch import FetchedPage


def test_audit_runner_combines_fetch_metadata_and_findings(monkeypatch):
    async def fake_fetch(url, **kwargs):
        return FetchedPage(
            requested_url=url,
            final_url="https://example.com/final",
            status_code=200,
            content_type="text/html",
            body="<html><head><title>Example</title></head><body><h1>Hi</h1></body></html>",
        )

    monkeypatch.setattr(website_audit_runner, "fetch_html", fake_fetch)
    report = asyncio.run(website_audit_runner.audit_website_url("https://example.com/start"))
    assert report["fetch"]["redirected"] is True
    assert report["fetch"]["final_url"] == "https://example.com/final"
    assert report["observations"]["title"] == "Example"
    assert any("Only one page" in limitation for limitation in report["limitations"])
