"""Read-only HTML SEO inspection for content obtained by a trusted fetch layer.

This module deliberately does not fetch URLs. Network retrieval needs a separately
hardened egress layer that validates DNS and every redirect, enforces byte/time
limits, and prevents DNS rebinding; callers must not treat this parser as an SSRF
protection boundary.
"""
from __future__ import annotations

import ipaddress
import json
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


def validate_page_url(value: str) -> str:
    """Validate URL syntax and reject non-public literal IPs and unsafe schemes.

    Hostname DNS resolution and redirect validation are intentionally outside this
    pure helper; a fetch layer must validate resolved addresses before connecting.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A page URL is required")
    value = value.strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Malformed page URL") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only http and https URLs are allowed")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must have a hostname and must not contain credentials")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid URL port")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("Localhost URLs are not allowed")
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Non-public IP addresses are not allowed")
    return value


class _SEOParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta: list[dict[str, str]] = []
        self.canonicals: list[str] = []
        self.headings: dict[str, list[str]] = {f"h{i}": [] for i in range(1, 7)}
        self.heading_tag: str | None = None
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.json_ld_blocks: list[str] = []
        self.in_json_ld = False
        self.json_ld_parts: list[str] = []
        self.viewport_present = False
        self.robots_values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            name = attr.get("name", "").lower()
            content = attr.get("content", "").strip()
            self.meta.append({"name": name, "content": content})
            if name == "viewport":
                self.viewport_present = True
            if name == "robots":
                self.robots_values.append(content.lower())
        elif tag == "link" and "canonical" in attr.get("rel", "").lower().split():
            if attr.get("href"):
                self.canonicals.append(attr["href"].strip())
        elif tag in self.headings:
            self.heading_tag = tag
        elif tag == "a":
            href = attr.get("href", "").strip()
            if href:
                self.links.append({"href": href, "text": ""})
        elif tag == "img":
            self.images.append({"src": attr.get("src", ""), "alt": attr.get("alt", "")})
        elif tag == "script" and attr.get("type", "").lower().split(";")[0].strip() == "application/ld+json":
            self.in_json_ld = True
            self.json_ld_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        if tag in self.headings and self.heading_tag == tag:
            self.heading_tag = None
        if tag == "script" and self.in_json_ld:
            self.json_ld_blocks.append("".join(self.json_ld_parts).strip())
            self.in_json_ld = False
            self.json_ld_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.heading_tag:
            self.headings[self.heading_tag].append(data.strip())
        if self.in_json_ld:
            self.json_ld_parts.append(data)


def analyze_html(*, page_url: str, html: str, status_code: int = 200) -> dict:
    """Return inspectable SEO observations from one already-fetched HTML document."""
    page_url = validate_page_url(page_url)
    if not isinstance(html, str):
        raise ValueError("HTML content must be text")
    parser = _SEOParser()
    parser.feed(html)
    parser.close()

    title = " ".join(" ".join(parser.title_parts).split())
    descriptions = [m["content"] for m in parser.meta if m["name"] == "description" and m["content"]]
    robots = " ".join(parser.robots_values)
    canonical_urls = [urljoin(page_url, href) for href in parser.canonicals]
    heading_text = {tag: [" ".join(x.split()) for x in values if x.strip()] for tag, values in parser.headings.items()}
    internal_links = []
    external_links = []
    page_host = (urlsplit(page_url).hostname or "").lower().rstrip(".")
    for link in parser.links:
        href = link["href"]
        if href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        absolute = urljoin(page_url, href)
        if urlsplit(absolute).scheme not in {"http", "https"}:
            continue
        host = (urlsplit(absolute).hostname or "").lower().rstrip(".")
        item = {"url": absolute, "anchor_text": link["text"].strip()}
        (internal_links if host == page_host else external_links).append(item)

    valid_json_ld = []
    invalid_json_ld_count = 0
    for block in parser.json_ld_blocks:
        try:
            parsed = json.loads(block)
            valid_json_ld.append({"valid_json": True, "top_level_type": type(parsed).__name__})
        except (json.JSONDecodeError, TypeError):
            invalid_json_ld_count += 1

    findings = []
    def finding(code: str, title_text: str, severity: str, detail: str) -> None:
        findings.append({"code": code, "title": title_text, "severity": severity, "evidence_url": page_url, "detail": detail})

    if status_code >= 400:
        finding("http_error_status", "Page returned an error status", "high", f"Observed HTTP status: {status_code}.")
    if not title:
        finding("missing_title", "Missing or empty title element", "medium", "No non-empty title text was found.")
    if len(descriptions) == 0:
        finding("missing_meta_description", "Missing meta description", "low", "No non-empty meta description was found.")
    elif len(descriptions) > 1:
        finding("duplicate_meta_description_tags", "Multiple meta description tags", "low", f"Observed {len(descriptions)} non-empty description tags.")
    if len(canonical_urls) > 1:
        finding("multiple_canonicals", "Multiple canonical declarations", "medium", f"Observed {len(canonical_urls)} canonical links.")
    if not parser.viewport_present:
        finding("missing_viewport", "Missing viewport meta tag", "medium", "No viewport meta declaration was found.")
    if "noindex" in {token.strip() for value in parser.robots_values for token in value.split(",")}:
        finding("robots_noindex", "Robots directive includes noindex", "high", "A robots meta directive contains noindex; verify this is intentional.")
    if not heading_text["h1"]:
        finding("missing_h1", "No H1 heading found", "low", "No non-empty H1 text was found.")
    missing_alt = sum(1 for img in parser.images if "alt" not in img or not img["alt"].strip())
    if missing_alt:
        finding("images_missing_alt", "Images missing alt text", "medium", f"{missing_alt} of {len(parser.images)} image elements have missing or empty alt attributes.")
    if invalid_json_ld_count:
        finding("invalid_json_ld", "Invalid JSON-LD block", "low", f"{invalid_json_ld_count} JSON-LD block(s) could not be parsed as JSON.")

    return {
        "page_url": page_url,
        "status_code": status_code,
        "observations": {
            "title": title or None,
            "title_length": len(title),
            "meta_descriptions": descriptions,
            "canonical_urls": canonical_urls,
            "robots_meta": parser.robots_values,
            "indexing_directive_observed": "noindex" if any("noindex" in v.split(",") for v in parser.robots_values) else "no_noindex_observed",
            "headings": heading_text,
            "viewport_meta_present": parser.viewport_present,
            "images_count": len(parser.images),
            "images_missing_alt_count": missing_alt,
            "internal_links": internal_links,
            "external_links": external_links,
            "json_ld_blocks_count": len(parser.json_ld_blocks),
            "json_ld_valid_blocks_count": len(valid_json_ld),
            "json_ld_invalid_blocks_count": invalid_json_ld_count,
        },
        "findings": findings,
        "limitations": [
            "This is a single-document HTML inspection, not a complete site crawl.",
            "HTML source inspection cannot confirm rendered DOM, Core Web Vitals, actual indexation, or search rankings.",
            "No network requests, page mutations, or publishing are performed by this module.",
            "A trusted fetch layer must enforce SSRF defenses, DNS/redirect validation, byte limits, and timeouts before passing content here.",
        ],
    }
