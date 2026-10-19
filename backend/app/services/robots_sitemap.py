"""Read-only parsers for robots.txt and XML sitemap documents.

These helpers inspect text already obtained by a trusted bounded fetch layer.
They do not make network requests and do not claim to verify search-engine indexing.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

from app.services.website_audit import validate_page_url


def analyze_robots_txt(*, robots_url: str, body: str, max_lines: int = 10_000) -> dict:
    """Summarize robots directives and Sitemap declarations from robots.txt text."""
    robots_url = validate_page_url(robots_url)
    if not isinstance(body, str):
        raise ValueError("robots.txt body must be text")
    lines = body.splitlines()
    if len(lines) > max_lines:
        raise ValueError("robots.txt exceeds the configured line limit")

    directives: list[dict[str, str]] = []
    sitemaps: list[str] = []
    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip().lower(), value.strip()
        if key == "sitemap" and value:
            absolute = urljoin(robots_url, value)
            sitemaps.append(validate_page_url(absolute))
        elif key in {"user-agent", "allow", "disallow", "crawl-delay", "host"}:
            directives.append({"directive": key, "value": value})

    groups: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for directive in directives:
        if directive["directive"] == "user-agent":
            current = {"user_agents": [directive["value"]], "rules": []}
            groups.append(current)
        elif current is not None:
            rules = current["rules"]
            assert isinstance(rules, list)
            rules.append(directive)

    disallow_all = any(
        rule["directive"] == "disallow" and rule["value"] == "/"
        for group in groups
        for rule in group["rules"]
    )
    return {
        "robots_url": robots_url,
        "line_count": len(lines),
        "groups": groups,
        "sitemap_urls": list(dict.fromkeys(sitemaps)),
        "disallow_root_rule_observed": disallow_all,
        "limitations": [
            "Robots directives are summarized as published; crawler-specific rule precedence is not fully evaluated.",
            "Robots.txt is a crawl directive, not access control and not a guarantee of de-indexing.",
        ],
    }


def analyze_sitemap_xml(*, sitemap_url: str, body: str, max_entries: int = 5_000) -> dict:
    """Parse a sitemap or sitemap index with bounded entry count."""
    sitemap_url = validate_page_url(sitemap_url)
    if not isinstance(body, str):
        raise ValueError("Sitemap body must be text")
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise ValueError("Sitemap XML is malformed") from exc

    root_name = root.tag.rsplit("}", 1)[-1].lower()
    if root_name not in {"urlset", "sitemapindex"}:
        raise ValueError("XML root must be urlset or sitemapindex")
    locations: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() == "loc" and element.text and element.text.strip():
            locations.append(validate_page_url(urljoin(sitemap_url, element.text.strip())))
            if len(locations) > max_entries:
                raise ValueError("Sitemap exceeds the configured entry limit")

    return {
        "sitemap_url": sitemap_url,
        "document_type": root_name,
        "entry_count": len(locations),
        "locations": locations,
        "same_host_locations_count": sum(
            1 for location in locations
            if (urlsplit(location).hostname or "").lower().rstrip(".")
            == (urlsplit(sitemap_url).hostname or "").lower().rstrip(".")
        ),
        "limitations": [
            "Presence in a sitemap does not prove that a URL is indexable or indexed.",
            "This parser does not recursively fetch sitemap indexes or verify each listed URL.",
        ],
    }
