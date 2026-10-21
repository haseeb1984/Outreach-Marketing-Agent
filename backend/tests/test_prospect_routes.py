from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import prospect_routes


def test_prospect_urls_must_use_https_and_credentials_are_rejected():
    assert prospect_routes._https_url("https://example.com/about") == "https://example.com/about"
    for value in (
        "http://example.com",
        "https://user:password@example.com",
        "javascript:alert(1)",
        "not-a-url",
    ):
        with pytest.raises(ValueError):
            prospect_routes._https_url(value)


def test_prospect_stage_is_allowlisted():
    assert prospect_routes.ProspectUpdate(workspace_id="w", stage="qualified").stage == "qualified"
    with pytest.raises(ValueError):
        prospect_routes.ProspectUpdate(workspace_id="w", stage="sent-everywhere")


def test_workspace_authorization_hides_unavailable_workspace():
    import asyncio

    class AuthStore:
        async def authorize_workspace(self, **kwargs):
            return False

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(auth_store=AuthStore())),
        cookies={prospect_routes._authenticated.__globals__["cookie_policy"].name: "session"},
    )

    async def authenticated(_request):
        return AuthStore(), "session", {"user_id": "00000000-0000-0000-0000-000000000001"}

    original = prospect_routes._authenticated
    prospect_routes._authenticated = authenticated
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(prospect_routes._authorize(request, "another-workspace", "viewer"))
        assert exc.value.status_code == 404
    finally:
        prospect_routes._authenticated = original


def test_prospect_create_schema_rejects_unbounded_or_extra_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        prospect_routes.ProspectCreate(
            workspace_id="workspace",
            name="Prospect",
            company="Company",
            website_url="https://example.com",
            evidence_url="https://example.com/source",
            fit_reason="Relevant public evidence",
            unapproved_send=True,
        )
    with pytest.raises(ValidationError):
        prospect_routes.ProspectCreate(
            workspace_id="workspace",
            name="Prospect",
            company="Company",
            website_url="http://example.com",
            evidence_url="https://example.com/source",
            fit_reason="Relevant public evidence",
        )
