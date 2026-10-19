"""Safe browser session-cookie and CSRF primitives; not complete middleware."""
from __future__ import annotations
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

class BrowserSecurityConfigurationError(ValueError):
    """Raised for unsafe cookie or CSRF configuration."""

@dataclass(frozen=True)
class SessionCookiePolicy:
    name: str = "__Host-oma_session"
    path: str = "/"
    secure: bool = True
    httponly: bool = True
    samesite: str = "lax"

    def __post_init__(self) -> None:
        if self.name != "__Host-oma_session":
            raise BrowserSecurityConfigurationError("invalid_session_cookie_name")
        if self.path != "/" or not self.secure or not self.httponly:
            raise BrowserSecurityConfigurationError("unsafe_session_cookie_policy")
        if self.samesite.lower() not in {"lax", "strict"}:
            raise BrowserSecurityConfigurationError("unsafe_session_cookie_samesite")

    def set_cookie_header(self, token: str, *, max_age: int) -> str:
        if not isinstance(token, str) or not 32 <= len(token) <= 512:
            raise ValueError("invalid_session_token")
        if isinstance(max_age, bool) or not isinstance(max_age, int) or not 1 <= max_age <= 2_592_000:
            raise ValueError("invalid_session_max_age")
        return f"{self.name}={token}; Path=/; Max-Age={max_age}; Secure; HttpOnly; SameSite={self.samesite.capitalize()}"

    def clear_cookie_header(self) -> str:
        return f"{self.name}=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite={self.samesite.capitalize()}"

def new_csrf_token() -> str:
    """Return a random synchronizer token; store it server-side and never log it."""
    return secrets.token_urlsafe(32)

def csrf_token_digest(token: str) -> str:
    if not isinstance(token, str) or not 32 <= len(token) <= 512:
        raise ValueError("invalid_csrf_token")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def verify_csrf_token(candidate: str, stored_digest: str) -> bool:
    if not isinstance(stored_digest, str) or len(stored_digest) != 64:
        return False
    try:
        actual = csrf_token_digest(candidate)
    except ValueError:
        return False
    return hmac.compare_digest(actual, stored_digest)

def origin_matches(request_origin: str | None, expected_origin: str) -> bool:
    """Require exact HTTPS origin equality; expected_origin must come from config."""
    if not isinstance(request_origin, str) or not isinstance(expected_origin, str):
        return False

    def normalize(value: str) -> str | None:
        value = value.strip()
        if not value or any(ch in value for ch in "\\r\\n\\\\"):
            return None
        try:
            parsed = urlsplit(value)
            # Origin headers contain only scheme + authority; permit a single trailing slash
            # for configured origins, but reject paths, query strings, fragments, and userinfo.
            if parsed.scheme.lower() != "https" or not parsed.hostname:
                return None
            if parsed.username is not None or parsed.password is not None:
                return None
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                return None
            port = parsed.port
            host = parsed.hostname.lower()
            return f"https://{host}" + (f":{port}" if port is not None and port != 443 else "")
        except ValueError:
            return None

    actual = normalize(request_origin)
    expected = normalize(expected_origin)
    return actual is not None and expected is not None and actual == expected
