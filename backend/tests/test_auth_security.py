import pytest
from app.services.auth_security import constant_time_token_match, hash_password, new_opaque_token, normalize_email, token_digest, verify_password

def test_normalize_email_trims_and_lowercases():
    assert normalize_email("  Person@Example.COM ") == "person@example.com"

@pytest.mark.parametrize("email", ["", "not-an-email", "a @example.com", "x" * 321])
def test_normalize_email_rejects_invalid_values(email):
    with pytest.raises(ValueError): normalize_email(email)

def test_password_hash_is_salted_and_verifies():
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first.encoded != second.encoded
    assert verify_password("correct horse battery staple", first.encoded)
    assert not verify_password("wrong password", first.encoded)

@pytest.mark.parametrize("password", ["short", "x" * 1025])
def test_password_length_is_bounded(password):
    with pytest.raises(ValueError): hash_password(password)

def test_password_verifier_rejects_malformed_or_unsafe_parameters():
    assert not verify_password("whatever password", "scrypt$999999999$8$1$aa$bb")
    assert not verify_password("whatever password", "not-a-hash")

def test_opaque_tokens_are_high_entropy_and_only_digest_is_stored():
    token = new_opaque_token()
    digest = token_digest(token)
    assert token not in digest
    assert constant_time_token_match(token, digest)
    assert not constant_time_token_match(new_opaque_token(), digest)


def test_dummy_password_hash_is_valid_and_not_a_user_credential():
    from app.services.auth_security import dummy_password_hash

    encoded = dummy_password_hash()
    assert verify_password("oma-internal-dummy-password-never-use-for-login", encoded)
    assert not verify_password("a real user's password", encoded)
