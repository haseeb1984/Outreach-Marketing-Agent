import pytest

from app.services.website_audit import analyze_html, validate_page_url


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com",
    "http://localhost/admin",
    "http://127.0.0.1/",
    "http://10.0.0.2/",
    "http://[::1]/",
    "http://user:pass@example.com/",
    "https://example.com:99999/",
])
def test_url_validator_rejects_unsafe_or_malformed_urls(url):
    with pytest.raises(ValueError):
        validate_page_url(url)


def test_url_validator_accepts_http_and_https_public_hostnames():
    assert validate_page_url("https://example.com/path") == "https://example.com/path"
    assert validate_page_url("http://example.org") == "http://example.org"


def test_html_audit_extracts_observations_and_reports_evidence():
    html = """
    <!doctype html><html><head>
      <title>  Helpful Local Service  </title>
      <meta name="description" content="A useful description">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <link rel="canonical" href="/services">
      <script type="application/ld+json">{"@type":"LocalBusiness"}</script>
    </head><body>
      <h1>Services</h1><h2>Our work</h2>
      <img src="/photo.jpg"><img src="/logo.svg" alt="Company logo">
      <a href="/contact">Contact</a><a href="https://other.example/about">Partner</a>
    </body></html>
    """
    result = analyze_html(page_url="https://example.com/services", html=html)
    observations = result["observations"]
    assert observations["title"] == "Helpful Local Service"
    assert observations["canonical_urls"] == ["https://example.com/services"]
    assert observations["viewport_meta_present"] is True
    assert observations["images_missing_alt_count"] == 1
    assert observations["json_ld_valid_blocks_count"] == 1
    assert len(observations["internal_links"]) == 1
    assert len(observations["external_links"]) == 1
    assert "images_missing_alt" in {finding["code"] for finding in result["findings"]}
    assert all(finding["evidence_url"] == "https://example.com/services" for finding in result["findings"])


def test_html_audit_flags_noindex_missing_metadata_and_invalid_jsonld():
    result = analyze_html(
        page_url="https://example.com/",
        status_code=200,
        html='<html><head><meta name="robots" content="noindex,follow"><script type="application/ld+json">{bad}</script></head><body><img src="/x"></body></html>',
    )
    codes = {finding["code"] for finding in result["findings"]}
    assert {"robots_noindex", "missing_title", "missing_meta_description", "missing_h1", "invalid_json_ld", "images_missing_alt"} <= codes
    assert result["observations"]["indexing_directive_observed"] == "noindex"


def test_audit_rejects_non_text_html():
    with pytest.raises(ValueError, match="HTML content"):
        analyze_html(page_url="https://example.com", html=None)
