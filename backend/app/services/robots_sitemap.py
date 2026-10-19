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


def evaluate_robots_path(*, body: str, path: str, user_agent: str = "*") -> dict:
    """Evaluate Allow/Disallow rules for one path using longest-match precedence.

    This is a deliberately small robots.txt evaluator for ordinary path rules,
    '*' wildcards, and '$' end anchors. If no rule matches, access is allowed.
    Callers must decide fail-closed behavior when robots.txt cannot be retrieved.
    """
    import re

    if not isinstance(body, str):
        raise ValueError("robots.txt body must be text")
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("path must be an absolute URL path beginning with '/'")
    if not user_agent.strip():
        raise ValueError("user_agent is required")

    # Build groups while merging consecutive User-agent lines before any rule.
    groups: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    saw_rule = False
    for raw_line in body.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key, value = key.lower(), value
        if key == "user-agent":
            if current is None or saw_rule:
                current = {"agents": [], "rules": []}
                groups.append(current)
                saw_rule = False
            agents = current["agents"]
            assert isinstance(agents, list)
            agents.append(value.lower())
        elif key in {"allow", "disallow"} and current is not None:
            # An empty Disallow means no restriction; an empty Allow matches nothing.
            if value:
                rules = current["rules"]
                assert isinstance(rules, list)
                rules.append((key, value))
                saw_rule = True

    ua = user_agent.lower()
    matching_groups: list[tuple[int, dict[str, object]]] = []
    for group in groups:
        agents = group["agents"]
        assert isinstance(agents, list)
        matches = [agent for agent in agents if agent == "*" or (agent and agent in ua)]
        if matches:
            specificity = max((len(agent) for agent in matches if agent != "*"), default=0)
            matching_groups.append((specificity, group))

    if not matching_groups:
        return {"allowed": True, "matched_rule": None, "reason": "no_matching_user_agent_group"}

    best_specificity = max(item[0] for item in matching_groups)
    rules_to_check: list[tuple[str, str]] = []
    for specificity, group in matching_groups:
        if specificity != best_specificity:
            continue
        rules = group["rules"]
        assert isinstance(rules, list)
        rules_to_check.extend(rules)

    candidate_path = path
    matching_rules: list[tuple[int, int, str, str]] = []
    for directive, pattern in rules_to_check:
        # Robots path matching is case-sensitive; '*' matches any sequence and '$'
        # anchors the end. Other regex metacharacters are treated literally.
        expression = re.escape(pattern).replace(r"\*", ".*")
        if expression.endswith(r"\$"):
            expression = expression[:-2] + "$"
        else:
            expression = expression + ".*"
        try:
            matched = re.match(expression, candidate_path) is not None
        except re.error:
            matched = False
        if matched:
            specificity_length = len(pattern.replace("*", "").replace("$", ""))
            # Allow wins equal-length ties.
            allow_tiebreak = 1 if directive == "allow" else 0
            matching_rules.append((specificity_length, allow_tiebreak, directive, pattern))

    if not matching_rules:
        return {"allowed": True, "matched_rule": None, "reason": "no_matching_rule"}

    specificity_length, _, directive, pattern = max(matching_rules, key=lambda rule: (rule[0], rule[1]))
    return {
        "allowed": directive == "allow",
        "matched_rule": {"directive": directive, "pattern": pattern, "specificity": specificity_length},
        "reason": "longest_matching_rule",
    }
