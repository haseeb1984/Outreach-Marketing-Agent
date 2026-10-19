import pytest
from app.services.auth_http_security import (
    BrowserSecurityConfigurationError, SessionCookiePolicy, csrf_token_digest,
    new_csrf_token, origin_matches, verify_csrf_token,
)

def test_session_cookie_is_secure_host_only_and_http_only():
    header = SessionCookiePolicy().set_cookie_header("x" * 43, max_age=3600)
    assert header.startswith("__Host-oma_session=")
    assert "Path=/" in header and "Secure" in header and "HttpOnly" in header
    assert "SameSite=Lax" in header and "Domain=" not in header

def test_session_cookie_rejects_unsafe_policy():
    with pytest.raises(BrowserSecurityConfigurationError): SessionCookiePolicy(secure=False)
    with pytest.raises(BrowserSecurityConfigurationError): SessionCookiePolicy(samesite="none")

def test_session_cookie_rejects_invalid_token_and_lifetime():
    policy = SessionCookiePolicy()
    with pytest.raises(ValueError): policy.set_cookie_header("short", max_age=3600)
    with pytest.raises(ValueError): policy.set_cookie_header("x" * 43, max_age=0)

def test_csrf_token_is_random_and_verified_using_digest():
    first, second = new_csrf_token(), new_csrf_token()
    assert first != second
    digest = csrf_token_digest(first)
    assert len(digest) == 64 and verify_csrf_token(first, digest)
    assert not verify_csrf_token(second, digest)
    assert not verify_csrf_token("bad", digest)

def test_origin_check_requires_exact_https_origin():
    assert origin_matches("https://app.example.com", "https://app.example.com/")
    assert not origin_matches("http://app.example.com", "https://app.example.com")
    assert not origin_matches("https://app.example.com.attacker.test", "https://app.example.com")
    assert not origin_matches("https://user@app.example.com", "https://app.example.com")
    assert not origin_matches("https://app.example.com/path", "https://app.example.com")
    assert origin_matches("https://app.example.com:443", "https://app.example.com/")
    assert not origin_matches("null", "https://app.example.com")
