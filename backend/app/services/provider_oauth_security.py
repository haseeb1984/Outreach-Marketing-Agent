"""Provider OAuth protocol primitives. No network calls or provider credentials live here."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from urllib.parse import urlsplit

_VERIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_STATE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_CODE_RE = re.compile(r"^[A-Za-z0-9._~+/-]{1,2048}$")


class ProviderOAuthSecurityError(ValueError):
    """An OAuth input or deployment configuration violates the security policy."""


def create_pkce_pair() -> tuple[str, str]:
    """Create an RFC 7636 verifier and its S256 challenge."""
    verifier = secrets.token_urlsafe(64)
    if not _VERIFIER_RE.fullmatch(verifier):
        raise RuntimeError("pkce_verifier_generation_failed")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def validate_redirect_uri(candidate: str, *, allowed_uris: tuple[str, ...] | list[str]) -> str:
    """Require exact match to a configured HTTPS callback; never normalize attacker input."""
    if not isinstance(candidate, str) or not candidate or len(candidate) > 2048:
        raise ProviderOAuthSecurityError("invalid_redirect_uri")
    try:
        parsed = urlsplit(candidate)
        valid_shape = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.fragment == ""
            and not any(character.isspace() for character in candidate)
        )
        # Force malformed port/authority errors now, not in a later redirect.
        _ = parsed.port
    except ValueError:
        valid_shape = False
    if not valid_shape or candidate not in allowed_uris:
        raise ProviderOAuthSecurityError("redirect_uri_not_allowlisted")
    return candidate


def validate_callback_parameters(*, state: str, code: str | None, error: str | None) -> str:
    """Validate shape and mutually exclusive success/error callback parameters."""
    if not isinstance(state, str) or not _STATE_RE.fullmatch(state):
        raise ProviderOAuthSecurityError("invalid_oauth_state")
    if error is not None:
        if not isinstance(error, str) or not 1 <= len(error) <= 128 or any(ord(c) < 32 for c in error):
            raise ProviderOAuthSecurityError("invalid_oauth_error")
        if code is not None:
            raise ProviderOAuthSecurityError("ambiguous_oauth_callback")
        raise ProviderOAuthSecurityError("provider_authorization_denied")
    if not isinstance(code, str) or not _CODE_RE.fullmatch(code):
        raise ProviderOAuthSecurityError("invalid_authorization_code")
    return code


def nonce_matches(candidate: str, expected_sha256: str) -> bool:
    """Constant-time compare a nonce to its persisted lowercase SHA-256 digest."""
    if not isinstance(candidate, str) or not 32 <= len(candidate) <= 512:
        return False
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        return False
    actual = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    return hmac.compare_digest(actual, expected_sha256)
