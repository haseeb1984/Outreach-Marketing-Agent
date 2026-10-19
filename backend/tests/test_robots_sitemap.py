import pytest

from app.services.robots_sitemap import analyze_robots_txt, analyze_sitemap_xml


def test_robots_parser_extracts_groups_and_sitemap_urls():
    result = analyze_robots_txt(
        robots_url="https://example.com/robots.txt",
        body="""User-agent: *
Disallow: /private/
Allow: /private/public/
Sitemap: /sitemap.xml
""",
    )
    assert result["sitemap_urls"] == ["https://example.com/sitemap.xml"]
    assert result["groups"][0]["user_agents"] == ["*"]
    assert [r["directive"] for r in result["groups"][0]["rules"]] == ["disallow", "allow"]
    assert result["disallow_root_rule_observed"] is False


def test_robots_parser_flags_root_disallow_and_limits_lines():
    result = analyze_robots_txt(robots_url="https://example.com/robots.txt", body="User-agent: *\nDisallow: /")
    assert result["disallow_root_rule_observed"] is True
    with pytest.raises(ValueError, match="line limit"):
        analyze_robots_txt(robots_url="https://example.com/robots.txt", body="a\nb", max_lines=1)


def test_sitemap_parser_handles_namespaces_and_sitemap_index():
    result = analyze_sitemap_xml(
        sitemap_url="https://example.com/sitemap-index.xml",
        body="""<?xml version="1.0"?>
        <s:sitemapindex xmlns:s="http://www.sitemaps.org/schemas/sitemap/0.9">
          <s:sitemap><s:loc>https://example.com/sitemap-a.xml</s:loc></s:sitemap>
          <s:sitemap><s:loc>https://cdn.example.net/sitemap-b.xml</s:loc></s:sitemap>
        </s:sitemapindex>""",
    )
    assert result["document_type"] == "sitemapindex"
    assert result["entry_count"] == 2
    assert result["same_host_locations_count"] == 1


def test_sitemap_parser_rejects_malformed_xml_unsafe_urls_and_entry_overflow():
    with pytest.raises(ValueError, match="malformed"):
        analyze_sitemap_xml(sitemap_url="https://example.com/sitemap.xml", body="<urlset>")
    with pytest.raises(ValueError):
        analyze_sitemap_xml(
            sitemap_url="https://example.com/sitemap.xml",
            body="<urlset><url><loc>http://127.0.0.1/admin</loc></url></urlset>",
        )
    with pytest.raises(ValueError, match="entry limit"):
        analyze_sitemap_xml(
            sitemap_url="https://example.com/sitemap.xml",
            body="<urlset><url><loc>/a</loc></url><url><loc>/b</loc></url></urlset>",
            max_entries=1,
        )
