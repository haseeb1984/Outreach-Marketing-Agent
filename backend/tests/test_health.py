from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_homepage_is_crawlable_html_and_discloses_development_status() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<html lang="en">' in response.text
    assert '<meta name="description"' in response.text
    assert "not yet available" in response.text
    assert 'href="/product"' in response.text


def test_public_product_pages_have_titles_and_descriptions() -> None:
    for path in ("/product", "/pricing", "/faq"):
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<title>" in response.text
        assert '<meta name="description"' in response.text


def test_llms_txt_lists_only_public_discovery_content() -> None:
    response = client.get("/llms.txt")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "/product" in response.text
    assert "not a" in response.text.lower()
    assert "planned features are not live" in response.text


def test_robots_txt_does_not_claim_to_secure_private_routes() -> None:
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Disallow: /dashboard" in response.text
    assert "Disallow: /billing" in response.text


def test_sitemap_requires_configured_public_origin(monkeypatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", None)
    response = client.get("/sitemap.xml")
    assert response.status_code == 503
    assert "PUBLIC_BASE_URL" in response.text


def test_sitemap_uses_configured_origin_and_only_public_pages(monkeypatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "https://marketing.example")
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    assert "https://marketing.example/" in response.text
    assert "https://marketing.example/pricing" in response.text
    assert "/dashboard" not in response.text
    assert "/billing" not in response.text


def test_api_info_points_to_api_docs() -> None:
    response = client.get("/api-info")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"
