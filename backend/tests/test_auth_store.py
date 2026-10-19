import pytest
from app.services.auth_store import ALLOWED_ROLES, ROLE_RANK


def test_workspace_role_hierarchy_is_explicit_and_ordered():
    assert ALLOWED_ROLES == {"owner", "admin", "member", "viewer"}
    assert ROLE_RANK["viewer"] < ROLE_RANK["member"] < ROLE_RANK["admin"] < ROLE_RANK["owner"]


def test_role_hierarchy_has_no_implicit_unknown_role():
    assert "superuser" not in ROLE_RANK
