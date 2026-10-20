from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import auth_routes


def test_auth_origin_requires_configured_https_origin(monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test/base/path")
    assert auth_routes._origin_from_config() == "https://app.example.test"
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "http://app.example.test")
    assert auth_routes._origin_from_config() is None
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://user@app.example.test")
    assert auth_routes._origin_from_config() is None
    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test/?bad=1")
    assert auth_routes._origin_from_config() is None


def test_csrf_cookie_is_secure_host_only_and_not_http_only():
    header = auth_routes._csrf_cookie("t" * 43, 3600)
    assert header.startswith("__Host-oma_csrf=")
    assert "Path=/" in header
    assert "Secure" in header
    assert "SameSite=Lax" in header
    assert "Domain=" not in header
    assert "HttpOnly" not in header
    with pytest.raises(ValueError):
        auth_routes._csrf_cookie("short", 3600)
    with pytest.raises(ValueError):
        auth_routes._csrf_cookie("t" * 43, 0)


def test_unsafe_request_requires_csrf_token_matching_server_digest(monkeypatch):
    monkeypatch.setattr(auth_routes, "_require_origin", lambda request: None)
    token = "a" * 43
    session = {"csrf_token_sha256": auth_routes.csrf_token_digest(token)}
    request = SimpleNamespace(headers={"x-csrf-token": token})
    auth_routes._check_csrf(request, session)
    request.headers = {"x-csrf-token": "b" * 43}
    with pytest.raises(HTTPException) as exc:
        auth_routes._check_csrf(request, session)
    assert exc.value.status_code == 403


def test_client_ip_does_not_trust_forwarded_header():
    request = SimpleNamespace(
        client=SimpleNamespace(host="192.0.2.10"),
        headers={"x-forwarded-for": "203.0.113.25"},
    )
    assert auth_routes._client_identifier(request) == "192.0.2.10"


@pytest.mark.asyncio
async def test_verification_landing_requires_explicit_post(monkeypatch):
    response = await auth_routes.verification_landing(token="v" * 43)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    html = response.body.decode()
    assert "fetch('/api/v1/auth/verify-email'" in html
    assert "method:'POST'" in html
    assert 'form method="post"' not in html
