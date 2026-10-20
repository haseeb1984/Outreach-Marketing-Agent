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


def test_verification_landing_requires_explicit_post(monkeypatch):
    import asyncio
    response = asyncio.run(auth_routes.verification_landing(token="v" * 43))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    html = response.body.decode()
    assert "fetch('/api/v1/auth/verify-email'" in html
    assert "method:'POST'" in html
    assert 'form method="post"' not in html



def test_http_login_sets_session_and_csrf_cookies_and_logout_revokes(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient
    from app.main import app

    csrf = "c" * 43
    session_token = "s" * 43
    user_id = "00000000-0000-0000-0000-000000000001"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    class FakeStore:
        revoked = False

        async def authenticate_password(self, *, email, password):
            if email == "person@example.test" and password == "correct-password":
                return {"user_id": user_id, "email": email}
            return None

        async def create_session(self, **kwargs):
            return {"token": session_token, "csrf_token": csrf, "expires_at": expires_at}

        async def authenticate_session(self, token):
            if token != session_token or self.revoked:
                return None
            return {
                "user_id": user_id,
                "email": "person@example.test",
                "session_id": "session-id",
                "expires_at": expires_at,
                "csrf_token_sha256": auth_routes.csrf_token_digest(csrf),
            }

        async def revoke_session(self, token):
            self.revoked = token == session_token
            return self.revoked

    class FakeLimiter:
        async def consume(self, **kwargs):
            return {
                "allowed": True,
                "remaining": 9,
                "reset_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            }

    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = FakeStore()
        app.state.auth_rate_limiter = FakeLimiter()
        login_response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://app.example.test"},
            json={"email": "person@example.test", "password": "correct-password"},
        )
        assert login_response.status_code == 200
        assert login_response.json()["csrf_token"] == csrf
        assert "__Host-oma_session" in login_response.headers.get("set-cookie", "")
        assert "__Host-oma_csrf" in login_response.headers.get("set-cookie", "")

        me_response = client.get("/api/v1/auth/me")
        assert me_response.status_code == 200
        assert me_response.json()["csrf_token"] == csrf

        logout_response = client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": csrf},
        )
        assert logout_response.status_code == 200
        assert app.state.auth_store.revoked is True
        assert "__Host-oma_session=;" in logout_response.headers.get("set-cookie", "")


def test_http_login_rejects_untrusted_origin(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://attacker.example.test"},
            json={"email": "person@example.test", "password": "correct-password"},
        )
        assert response.status_code == 403
