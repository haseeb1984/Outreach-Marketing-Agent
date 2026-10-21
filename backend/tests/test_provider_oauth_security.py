import base64
import hashlib

import pytest

from app.services.provider_oauth_security import (
    ProviderOAuthSecurityError,
    create_pkce_pair,
    nonce_matches,
    validate_callback_parameters,
    validate_redirect_uri,
)


def test_pkce_pair_uses_s256_and_verifier_is_not_the_challenge():
    verifier, challenge = create_pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    assert 43 <= len(verifier) <= 128
    assert challenge == expected
    assert verifier != challenge


def test_redirect_uri_requires_exact_https_allowlist_match():
    allowed = ["https://app.example.test/oauth/email/callback"]
    assert validate_redirect_uri(allowed[0], allowed_uris=allowed) == allowed[0]
    for candidate in (
        "http://app.example.test/oauth/email/callback",
        "https://app.example.test.attacker.test/oauth/email/callback",
        "https://user@app.example.test/oauth/email/callback",
        "https://app.example.test/oauth/email/callback/",
        "https://app.example.test/oauth/email/callback#fragment",
    ):
        with pytest.raises(ProviderOAuthSecurityError):
            validate_redirect_uri(candidate, allowed_uris=allowed)


def test_callback_parameters_require_valid_state_and_exclusive_code_or_error():
    state = "S" * 43
    assert validate_callback_parameters(state=state, code="auth_code_123", error=None) == "auth_code_123"
    with pytest.raises(ProviderOAuthSecurityError):
        validate_callback_parameters(state="short", code="auth_code_123", error=None)
    with pytest.raises(ProviderOAuthSecurityError):
        validate_callback_parameters(state=state, code="auth_code_123", error="access_denied")
    with pytest.raises(ProviderOAuthSecurityError, match="provider_authorization_denied"):
        validate_callback_parameters(state=state, code=None, error="access_denied")
    with pytest.raises(ProviderOAuthSecurityError):
        validate_callback_parameters(state=state, code=None, error=None)


def test_nonce_verification_is_digest_based_and_fails_closed():
    nonce = "N" * 43
    digest = hashlib.sha256(nonce.encode()).hexdigest()
    assert nonce_matches(nonce, digest)
    assert not nonce_matches("X" * 43, digest)
    assert not nonce_matches(nonce, "not-a-digest")
