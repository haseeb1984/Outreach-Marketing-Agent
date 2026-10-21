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

def test_http_login_rate_limit_blocks_password_verification(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient
    from app.main import app

    class NeverAuthenticateStore:
        async def authenticate_password(self, **kwargs):
            raise AssertionError("password verification must not run after rate limit")

    class BlockingLimiter:
        async def consume(self, **kwargs):
            return {
                "allowed": False,
                "remaining": 0,
                "reset_at": datetime.now(timezone.utc) + timedelta(minutes=2),
            }

    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = NeverAuthenticateStore()
        app.state.auth_rate_limiter = BlockingLimiter()
        response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://app.example.test"},
            json={"email": "person@example.test", "password": "correct-password"},
        )
        assert response.status_code == 429
        assert response.json()["detail"] == "too_many_requests"
        assert int(response.headers["retry-after"]) >= 1


def test_http_login_fails_closed_when_rate_limiter_unavailable(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    class UnavailableLimiter:
        async def consume(self, **kwargs):
            raise RuntimeError("database details must not reach the client")

    class NeverAuthenticateStore:
        async def authenticate_password(self, **kwargs):
            raise AssertionError("password verification must not run")

    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = NeverAuthenticateStore()
        app.state.auth_rate_limiter = UnavailableLimiter()
        response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://app.example.test"},
            json={"email": "person@example.test", "password": "correct-password"},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "authentication_temporarily_unavailable"
        assert "database details" not in response.text

def test_http_session_rotation_replaces_both_cookies_and_csrf_token(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient
    from app.main import app

    old_csrf, new_csrf = "o" * 43, "n" * 43
    old_session, new_session = "s" * 43, "r" * 43
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    class RotatingStore:
        current_token = old_session

        async def authenticate_session(self, token):
            if token != self.current_token:
                return None
            return {
                "user_id": "00000000-0000-0000-0000-000000000001",
                "email": "person@example.test",
                "session_id": "session-id",
                "expires_at": expires_at,
                "csrf_token_sha256": auth_routes.csrf_token_digest(old_csrf),
            }

        async def rotate_session(self, **kwargs):
            assert kwargs["current_token"] == old_session
            self.current_token = new_session
            return {"token": new_session, "csrf_token": new_csrf, "expires_at": expires_at}

    class AllowLimiter:
        async def consume(self, **kwargs):
            return {"allowed": True, "remaining": 9, "reset_at": expires_at}

    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = RotatingStore()
        app.state.auth_rate_limiter = AllowLimiter()
        client.cookies.set("__Host-oma_session", old_session)
        client.cookies.set("__Host-oma_csrf", old_csrf)

        response = client.post(
            "/api/v1/auth/rotate",
            headers={"Origin": "https://app.example.test", "X-CSRF-Token": old_csrf},
        )
        assert response.status_code == 200
        assert response.json()["csrf_token"] == new_csrf
        cookies = response.headers.get_list("set-cookie")
        assert any(value.startswith("__Host-oma_session=" + new_session) for value in cookies)
        assert any(value.startswith("__Host-oma_csrf=" + new_csrf) for value in cookies)
        import asyncio
        assert asyncio.run(app.state.auth_store.authenticate_session(old_session)) is None
        assert client.get("/api/v1/auth/me").status_code == 200



def test_password_reset_request_is_generic_and_sends_only_when_store_issues_token(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient
    from app.main import app

    sent = []
    class ResetStore:
        async def issue_password_reset(self, *, email):
            if email == "person@example.test":
                return {
                    "reset_token": "r" * 43,
                    "expires_at": datetime.now(timezone.utc) + timedelta(minutes=30),
                }
            return None

    class AllowLimiter:
        async def consume(self, **kwargs):
            return {
                "allowed": True,
                "remaining": 9,
                "reset_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            }

    async def fake_send(self, **kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    monkeypatch.setattr(auth_routes.SMTPEmailDelivery, "send_password_reset_email", fake_send)
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = ResetStore()
        app.state.auth_rate_limiter = AllowLimiter()
        headers = {"Origin": "https://app.example.test"}
        known = client.post(
            "/api/v1/auth/password-reset/request", headers=headers,
            json={"email": "person@example.test"},
        )
        unknown = client.post(
            "/api/v1/auth/password-reset/request", headers=headers,
            json={"email": "unknown@example.test"},
        )
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert len(sent) == 1
        assert sent[0]["recipient"] == "person@example.test"


def test_password_reset_confirm_updates_password_and_rejects_invalid_token(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    class ResetStore:
        async def reset_password(self, *, token, new_password):
            assert len(new_password) >= 12
            return token == "r" * 43

    class AllowLimiter:
        async def consume(self, **kwargs):
            from datetime import datetime, timedelta, timezone
            return {
                "allowed": True, "remaining": 9,
                "reset_at": datetime.now(timezone.utc) + timedelta(minutes=15),
            }

    monkeypatch.setattr(auth_routes.settings, "public_base_url", "https://app.example.test")
    with TestClient(app, base_url="https://app.example.test") as client:
        app.state.auth_store = ResetStore()
        app.state.auth_rate_limiter = AllowLimiter()
        headers = {"Origin": "https://app.example.test"}
        good = client.post(
            "/api/v1/auth/password-reset/confirm", headers=headers,
            json={"token": "r" * 43, "new_password": "correct-horse-battery"},
        )
        bad = client.post(
            "/api/v1/auth/password-reset/confirm", headers=headers,
            json={"token": "x" * 43, "new_password": "correct-horse-battery"},
        )
        assert good.status_code == 200
        assert bad.status_code == 400
        assert "invalid_or_expired" in bad.json()["detail"]


def test_password_reset_landing_requires_explicit_form_submission():
    import asyncio

    response = asyncio.run(auth_routes.password_reset_landing(token="r" * 43))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    html = response.body.decode()
    assert "password-reset/confirm" in html
    assert "method:'POST'" in html
    assert "autocomplete=\"new-password\"" in html

    invalid = asyncio.run(auth_routes.password_reset_landing(token="short"))
    assert invalid.status_code == 400
