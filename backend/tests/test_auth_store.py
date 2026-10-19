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
