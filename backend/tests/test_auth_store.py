import pytest
from app.services.auth_store import ALLOWED_ROLES, ROLE_RANK


def test_workspace_role_hierarchy_is_explicit_and_ordered():
    assert ALLOWED_ROLES == {"owner", "admin", "member", "viewer"}
    assert ROLE_RANK["viewer"] < ROLE_RANK["member"] < ROLE_RANK["admin"] < ROLE_RANK["owner"]


def test_role_hierarchy_has_no_implicit_unknown_role():
    assert "superuser" not in ROLE_RANK


def test_session_lifetime_is_bounded_before_database_access():
    import asyncio
    from app.services.auth_store import AuthStore

    store = AuthStore(None)
    for lifetime in (0, -1, 721, True, 1.5):
        with pytest.raises(ValueError, match="session_lifetime_out_of_range"):
            asyncio.run(store.create_session(user_id="00000000-0000-4000-8000-000000000001", lifetime_hours=lifetime))


def test_verification_rejects_malformed_token_without_database_access():
    import asyncio
    from app.services.auth_store import AuthStore

    assert asyncio.run(AuthStore(None).verify_email("too-short")) is False


def test_registration_rejects_invalid_email_before_database_access():
    import asyncio
    from app.services.auth_store import AuthStore

    with pytest.raises(ValueError, match="invalid_email"):
        asyncio.run(AuthStore(None).register_user(email="not-an-email", password="a long enough password"))


def test_rotation_lifetime_is_bounded_before_database_access():
    import asyncio
    from app.services.auth_store import AuthStore

    store = AuthStore(None)
    for lifetime in (0, -1, 721, True, 1.5):
        with pytest.raises(ValueError, match="session_lifetime_out_of_range"):
            asyncio.run(store.rotate_session(current_token="x" * 43, lifetime_hours=lifetime))


def test_rotation_rejects_malformed_token_without_database_access():
    import asyncio
    from app.services.auth_store import AuthStore

    assert asyncio.run(AuthStore(None).rotate_session(current_token="short")) is None


def test_password_reset_rejects_malformed_token_without_database_access():
    import asyncio
    from app.services.auth_store import AuthStore

    assert asyncio.run(AuthStore(None).reset_password(token="short", new_password="a valid long password")) is False


def test_password_reset_rejects_invalid_password_before_database_access():
    import asyncio
    from app.services.auth_store import AuthStore

    with pytest.raises(ValueError, match="password_length_out_of_range"):
        asyncio.run(AuthStore(None).reset_password(token="x" * 43, new_password="short"))


def test_password_reset_lifetime_is_bounded_before_database_access():
    import asyncio
    from app.services.auth_store import AuthStore

    store = AuthStore(None)
    for lifetime in (0, 4, 61, True, 1.5):
        with pytest.raises(ValueError, match="password_reset_lifetime_out_of_range"):
            asyncio.run(store.issue_password_reset(email="person@example.com", lifetime_minutes=lifetime))


def test_password_reset_issue_rejects_invalid_email_before_database_access():
    import asyncio
    from app.services.auth_store import AuthStore

    with pytest.raises(ValueError, match="invalid_email"):
        asyncio.run(AuthStore(None).issue_password_reset(email="not-an-email"))

class _CredentialConnection:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.args = None

    async def fetchrow(self, query, *args):
        self.query = query
        self.args = args
        return self.row


class _CredentialAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _CredentialPool:
    def __init__(self, row):
        self.connection = _CredentialConnection(row)

    def acquire(self):
        return _CredentialAcquire(self.connection)


def test_password_authentication_returns_only_safe_identity_for_verified_account():
    import asyncio
    from uuid import UUID
    from app.services.auth_security import hash_password
    from app.services.auth_store import AuthStore

    user_id = UUID("00000000-0000-4000-8000-000000000001")
    row = {
        "id": user_id,
        "email": "person@example.com",
        "password_hash": hash_password("correct horse battery staple").encoded,
    }
    pool = _CredentialPool(row)

    result = asyncio.run(AuthStore(pool).authenticate_password(
        email=" Person@Example.com ",
        password="correct horse battery staple",
    ))

    assert result == {"user_id": str(user_id), "email": "person@example.com"}
    assert "password_hash" not in result
    assert "status='active'" in pool.connection.query
    assert "email_verified_at IS NOT NULL" in pool.connection.query


def test_password_authentication_uses_generic_failure_for_invalid_credentials():
    import asyncio
    from app.services.auth_security import hash_password
    from app.services.auth_store import AuthStore

    pool = _CredentialPool({
        "id": "00000000-0000-4000-8000-000000000001",
        "email": "person@example.com",
        "password_hash": hash_password("correct horse battery staple").encoded,
    })
    store = AuthStore(pool)

    assert asyncio.run(store.authenticate_password(
        email="person@example.com", password="wrong password here"
    )) is None
    assert asyncio.run(store.authenticate_password(
        email="not-an-email", password="correct horse battery staple"
    )) is None
    assert asyncio.run(AuthStore(_CredentialPool(None)).authenticate_password(
        email="person@example.com", password="correct horse battery staple"
    )) is None



def test_password_authentication_checks_dummy_hash_for_missing_account(monkeypatch):
    import asyncio
    from app.services import auth_security
    from app.services.auth_store import AuthStore

    calls = []
    monkeypatch.setattr(auth_security, "verify_password", lambda password, encoded: calls.append(encoded) or False)
    monkeypatch.setattr(auth_security, "dummy_password_hash", lambda: "dummy-scrypt-hash")

    result = asyncio.run(AuthStore(_CredentialPool(None)).authenticate_password(
        email="person@example.com", password="candidate password"
    ))

    assert result is None
    assert calls == ["dummy-scrypt-hash"]
