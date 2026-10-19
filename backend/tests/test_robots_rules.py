import pytest

from app.services.robots_sitemap import evaluate_robots_path


def test_robots_longest_rule_wins_and_allow_wins_equal_length_tie():
    body = """User-agent: *
Disallow: /private/
Allow: /private/public/
Disallow: /same
Allow: /same
"""
    assert evaluate_robots_path(body=body, path="/private/account")["allowed"] is False
    result = evaluate_robots_path(body=body, path="/private/public/page")
    assert result["allowed"] is True
    assert evaluate_robots_path(body=body, path="/same")["allowed"] is True


def test_robots_supports_wildcard_end_anchor_and_user_agent_specificity():
    body = """User-agent: *
Disallow: /blocked
User-agent: ExampleBot
Disallow: /private
Allow: /private/public$
"""
    assert evaluate_robots_path(body=body, path="/blocked/x", user_agent="OtherBot")["allowed"] is False
    assert evaluate_robots_path(body=body, path="/private/x", user_agent="ExampleBot/1.0")["allowed"] is False
    assert evaluate_robots_path(body=body, path="/private/public", user_agent="ExampleBot/1.0")["allowed"] is True
    assert evaluate_robots_path(body=body, path="/private/public/x", user_agent="ExampleBot/1.0")["allowed"] is False


def test_robots_empty_disallow_is_not_a_block_and_invalid_path_is_rejected():
    assert evaluate_robots_path(body="User-agent: *\nDisallow:\n", path="/anything")["allowed"] is True
    with pytest.raises(ValueError, match="absolute URL path"):
        evaluate_robots_path(body="User-agent: *", path="relative")
