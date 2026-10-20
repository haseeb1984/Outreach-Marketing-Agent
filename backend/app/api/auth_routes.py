"""HTTP authentication endpoints; enabled only with a configured database and secrets.

Never log passwords, cookies, CSRF values, verification tokens, or provider exceptions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.services.auth_http_security import (
    SessionCookiePolicy, csrf_token_digest, origin_matches, verify_csrf_token,
)
from app.services.auth_rate_limiter import RateLimitConfigurationError
from app.services.auth_security import normalize_email
from app.services.email_delivery import (
    EmailDeliveryFailed, EmailDeliveryNotConfigured, SMTPEmailDelivery,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
cookie_policy = SessionCookiePolicy()


class RegistrationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class VerificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=512)


def _origin_from_config() -> str | None:
    value = settings.public_base_url
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            return None
        if parsed.query or parsed.fragment:
            return None
        port = parsed.port
        host = parsed.hostname.lower()
        return "https://" + host + (f":{port}" if port is not None and port != 443 else "")
    except ValueError:
        return None


def _require_origin(request: Request) -> None:
    expected = _origin_from_config()
    if expected is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    if not origin_matches(request.headers.get("origin"), expected):
        raise HTTPException(status_code=403, detail="request_origin_rejected")


def _services(request: Request):
    store = getattr(request.app.state, "auth_store", None)
    limiter = getattr(request.app.state, "auth_rate_limiter", None)
    if store is None or limiter is None:
        raise HTTPException(status_code=503, detail="authentication_not_configured")
    return store, limiter


def _client_identifier(request: Request) -> str:
    # Deliberately ignore forwarded headers; only trust them after explicit proxy configuration.
    return request.client.host if request.client and request.client.host else "unknown-client"


async def _consume(limiter, *, namespace: str, identifier: str, limit: int, window: int) -> None:
    try:
        result = await limiter.consume(
            namespace=namespace, identifier=identifier, limit=limit, window_seconds=window,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="authentication_temporarily_unavailable") from None
    if not result["allowed"]:
        raise HTTPException(
            status_code=429,
            detail="too_many_requests",
            headers={"Retry-After": str(max(1, int((result["reset_at"] - datetime.now(timezone.utc)).total_seconds())))},
        )


async def _authenticated(request: Request):
    store, _ = _services(request)
    token = request.cookies.get(cookie_policy.name)
    if not token:
        raise HTTPException(status_code=401, detail="authentication_required")
    session = await store.authenticate_session(token)
    if session is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    return store, token, session


def _check_csrf(request: Request, session: dict) -> None:
    _require_origin(request)
    candidate = request.headers.get("x-csrf-token", "")
    if not verify_csrf_token(candidate, session["csrf_token_sha256"]):
        raise HTTPException(status_code=403, detail="csrf_validation_failed")


@router.post("/register", status_code=202)
async def register(payload: RegistrationInput, request: Request):
    _require_origin(request)
    store, limiter = _services(request)
    ip = _client_identifier(request)
    await _consume(limiter, namespace="register-ip", identifier=ip, limit=5, window=3600)
    try:
        email = normalize_email(payload.email)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_registration_input") from None
    await _consume(limiter, namespace="register-email", identifier=email, limit=3, window=3600)
    delivery = SMTPEmailDelivery()
    try:
        delivery._validate_configuration()
    except EmailDeliveryNotConfigured:
        raise HTTPException(status_code=503, detail="email_delivery_not_configured") from None
    try:
        created = await store.register_user(email=email, password=payload.password)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid_registration_input") from None
    if created is not None:
        try:
            await delivery.send_verification_email(
                recipient=created["email"], token=created["verification_token"],
                expires_at=created["verification_expires_at"],
            )
        except (EmailDeliveryFailed, EmailDeliveryNotConfigured, ValueError):
            # The public response does not reveal whether an account was created.
            raise HTTPException(status_code=503, detail="verification_delivery_unavailable") from None
    return {"message": "If registration can proceed, a verification email will be sent."}


@router.post("/verify-email")
async def verify_email(payload: VerificationInput, request: Request):
    _require_origin(request)
    store, limiter = _services(request)
    await _consume(limiter, namespace="verify-ip", identifier=_client_identifier(request), limit=10, window=3600)
    try:
        valid = await store.verify_email(payload.token)
    except Exception:
        raise HTTPException(status_code=503, detail="verification_temporarily_unavailable") from None
    if not valid:
        raise HTTPException(status_code=400, detail="verification_link_invalid_or_expired")
    return {"message": "Email verified. You can now sign in."}


@router.get("/verify-email", response_class=HTMLResponse, include_in_schema=False)
async def verification_landing(token: str = "") -> HTMLResponse:
    # GET only displays a confirmation form. Token consumption happens on explicit POST,
    # avoiding link-scanner activation. Do not permit external resources or referrer leaks.
    safe_token = escape(token, quote=True) if 32 <= len(token) <= 512 else ""
    if not safe_token:
        return HTMLResponse(
            "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"referrer\" content=\"no-referrer\"></head><body><h1>Invalid verification link</h1><p>Request a new verification email if needed.</p></body></html>",
            status_code=400, headers={"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"},
        )
    html = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"referrer\" content=\"no-referrer\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Verify email</title></head><body><main><h1>Verify your email</h1>"
        "<p>Select the button to activate this verification link.</p>"
        "<form method=\"post\" action=\"/api/v1/auth/verify-email\">"
        f"<input type=\"hidden\" name=\"token\" value=\"{safe_token}\">"
        "<button type=\"submit\">Verify email</button></form></main></body></html>"
    )
    return HTMLResponse(html, headers={"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"})


@router.post("/login")
async def login(payload: LoginInput, request: Request):
    _require_origin(request)
    store, limiter = _services(request)
    ip = _client_identifier(request)
    await _consume(limiter, namespace="login-ip", identifier=ip, limit=20, window=900)
    email_identifier = payload.email.strip().lower()[:320] or "invalid"
    await _consume(limiter, namespace="login-email", identifier=email_identifier, limit=10, window=900)
    user = await store.authenticate_password(email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="email_or_password_incorrect")
    try:
        session = await store.create_session(
            user_id=user["user_id"], user_agent=request.headers.get("user-agent"),
            lifetime_hours=24,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="authentication_temporarily_unavailable") from None
    response = JSONResponse({
        "user": user,
        "csrf_token": session["csrf_token"],
        "expires_at": session["expires_at"].isoformat(),
    })
    max_age = max(1, int((session["expires_at"] - datetime.now(timezone.utc)).total_seconds()))
    response.headers.append("Set-Cookie", cookie_policy.set_cookie_header(session["token"], max_age=max_age))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/me")
async def me(request: Request):
    _, _, session = await _authenticated(request)
    return {
        "user": {"user_id": str(session["user_id"]), "email": session["email"]},
        "csrf_token_sha256": session["csrf_token_sha256"],
        "expires_at": session["expires_at"].isoformat(),
    }


@router.post("/rotate")
async def rotate(request: Request):
    store, token, session = await _authenticated(request)
    _check_csrf(request, session)
    try:
        replacement = await store.rotate_session(
            current_token=token, user_agent=request.headers.get("user-agent"),
            lifetime_hours=24,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="session_rotation_unavailable") from None
    if replacement is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    response = JSONResponse({
        "csrf_token": replacement["csrf_token"],
        "expires_at": replacement["expires_at"].isoformat(),
    })
    max_age = max(1, int((replacement["expires_at"] - datetime.now(timezone.utc)).total_seconds()))
    response.headers.append("Set-Cookie", cookie_policy.set_cookie_header(replacement["token"], max_age=max_age))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.post("/logout")
async def logout(request: Request):
    store, token, session = await _authenticated(request)
    _check_csrf(request, session)
    await store.revoke_session(token)
    response = JSONResponse({"message": "Signed out."})
    response.headers.append("Set-Cookie", cookie_policy.clear_cookie_header())
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
