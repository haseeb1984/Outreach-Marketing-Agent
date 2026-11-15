"""Regression tests for the campaign-to-human-approval-to-delivery lifecycle."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from app.api import campaign_routes


class _AuthStore:
    async def authorize_workspace(self, **kwargs):
        return True


class _Subscriptions:
    def __init__(self, reservations=None, finish_results=None, finish_error=None):
        self.reservations = list(reservations or [])
        self.finish_results = list(finish_results or [])
        self.finish_error = finish_error
        self.reserve_calls = []
        self.finish_calls = []

    async def reserve_usage(self, **kwargs):
        self.reserve_calls.append(kwargs)
        if not self.reservations:
            raise AssertionError("unexpected quota reservation")
        return self.reservations.pop(0)

    async def finish_reservation(self, **kwargs):
        self.finish_calls.append(kwargs)
        if self.finish_error:
            raise self.finish_error
        if self.finish_results:
            return self.finish_results.pop(0)
        return True


class _CampaignStore:
    def __init__(self, *, draft=None, review=None, review_error=None):
        self.draft = draft
        self.review = review
        self.review_error = review_error
        self.create_calls = []
        self.review_calls = []

    async def create_draft(self, **kwargs):
        self.create_calls.append(kwargs)
        if isinstance(self.draft, Exception):
            raise self.draft
        return self.draft

    async def review_draft(self, **kwargs):
        self.review_calls.append(kwargs)
        if self.review_error:
            raise self.review_error
        return self.review


def _request(*, subscriptions, campaign_store, user_id=None):
    app = FastAPI()
    app.state.auth_store = _AuthStore()
    app.state.subscription_store = subscriptions
    app.state.campaign_store = campaign_store
    actor = user_id or str(uuid4())
    return Request({
        "type": "http",
        "app": app,
        "method": "POST",
        "path": "/api/v1/drafts",
        "headers": [],
        "query_string": b"",
        "session": {},
    }), actor


def _payload():
    return campaign_routes.DraftCreate(
        workspace_id="workspace-a",
        campaign_id=uuid4(),
        prospect_id=uuid4(),
        channel="email",
        call_to_action="Would you be open to a short call?",
        idempotency_key="campaign-draft-001",
    )


def _patch_auth(monkeypatch, actor_id):
    async def authenticated(_request):
        return None, None, {"user_id": actor_id}

    monkeypatch.setattr(campaign_routes, "_authenticated", authenticated)
    monkeypatch.setattr(campaign_routes, "_check_csrf", lambda *_args: None)


def test_template_fallback_without_ai_provider_does_not_reserve_ai_quota(monkeypatch):
    actor_id = str(uuid4())
    draft = {"id": str(uuid4()), "status": "pending_approval", "channel": "email"}
    subscriptions = _Subscriptions()
    store = _CampaignStore(draft=draft)
    request, _ = _request(subscriptions=subscriptions, campaign_store=store, user_id=actor_id)
    _patch_auth(monkeypatch, actor_id)
    monkeypatch.setattr(campaign_routes.settings, "ai_api_key", "")

    result = asyncio.run(campaign_routes.create_draft(_payload(), request))

    assert result == draft
    assert subscriptions.reserve_calls == []
    assert subscriptions.finish_calls == []
    assert store.create_calls[0]["idempotency_key"] == "campaign-draft-001"


def test_template_fallback_is_available_when_ai_quota_is_exhausted(monkeypatch):
    actor_id = str(uuid4())
    draft = {"id": str(uuid4()), "status": "pending_approval", "channel": "email"}
    subscriptions = _Subscriptions(reservations=[{"allowed": False, "reason": "quota_exhausted"}])
    store = _CampaignStore(draft=draft)
    request, _ = _request(subscriptions=subscriptions, campaign_store=store, user_id=actor_id)
    _patch_auth(monkeypatch, actor_id)
    monkeypatch.setattr(campaign_routes.settings, "ai_api_key", "configured-ai-key")

    result = asyncio.run(campaign_routes.create_draft(_payload(), request))

    assert result == draft
    assert len(subscriptions.reserve_calls) == 1
    assert subscriptions.finish_calls == []
    assert store.create_calls[0]["generated_content"] is None
    assert store.create_calls[0]["idempotency_key"] == "campaign-draft-001"


@pytest.mark.parametrize("reason,status_code", [
    ("quota_exhausted", 429),
    ("subscription_inactive", 403),
    ("feature_disabled", 403),
])
def test_draft_generation_denial_never_creates_draft(monkeypatch, reason, status_code):
    actor_id = str(uuid4())
    subscriptions = _Subscriptions(reservations=[{"allowed": False, "reason": reason}])
    store = _CampaignStore(draft={"id": "must-not-exist"})
    request, _ = _request(subscriptions=subscriptions, campaign_store=store, user_id=actor_id)
    _patch_auth(monkeypatch, actor_id)

    with pytest.raises(HTTPException) as error:
        asyncio.run(campaign_routes.create_draft(_payload(), request))

    assert error.value.status_code == status_code
    assert store.create_calls == []
    assert subscriptions.finish_calls == []


@pytest.mark.parametrize("reason,status", [
    ("idempotent_replay", "reserved"),
    ("reserved", "consumed"),
])
def test_draft_generation_replay_does_not_create_duplicate(monkeypatch, reason, status):
    actor_id = str(uuid4())
    subscriptions = _Subscriptions(reservations=[{
        "allowed": True, "reason": reason, "status": status, "reservation_id": str(uuid4()),
    }])
    store = _CampaignStore(draft={"id": "must-not-exist"})
    request, _ = _request(subscriptions=subscriptions, campaign_store=store, user_id=actor_id)
    _patch_auth(monkeypatch, actor_id)

    with pytest.raises(HTTPException) as error:
        asyncio.run(campaign_routes.create_draft(_payload(), request))

    assert error.value.status_code == 409
    assert error.value.detail == "draft_generation_key_already_used"
    assert store.create_calls == []
    assert subscriptions.finish_calls == []


def test_invalid_draft_inputs_release_reserved_quota(monkeypatch):
    actor_id = str(uuid4())
    reservation_id = str(uuid4())
    subscriptions = _Subscriptions(
        reservations=[{"allowed": True, "reason": "reserved", "status": "reserved",
                       "reservation_id": reservation_id}],
    )
    store = _CampaignStore(draft=ValueError("prospect_email_required"))
    request, _ = _request(subscriptions=subscriptions, campaign_store=store, user_id=actor_id)
    _patch_auth(monkeypatch, actor_id)

    with pytest.raises(HTTPException) as error:
        asyncio.run(campaign_routes.create_draft(_payload(), request))

    assert error.value.status_code == 422
    assert error.value.detail == "prospect_email_required"
    assert subscriptions.finish_calls == [{
        "workspace_id": "workspace-a", "reservation_id": reservation_id, "outcome": "released",
    }]


def test_ambiguous_draft_persistence_consumes_quota_to_prevent_retry_bypass(monkeypatch):
    actor_id = str(uuid4())
    reservation_id = str(uuid4())
    subscriptions = _Subscriptions(
        reservations=[{"allowed": True, "reason": "reserved", "status": "reserved",
                       "reservation_id": reservation_id}],
    )
    store = _CampaignStore(draft=RuntimeError("database details must not leak"))
    request, _ = _request(subscriptions=subscriptions, campaign_store=store, user_id=actor_id)
    _patch_auth(monkeypatch, actor_id)

    with pytest.raises(HTTPException) as error:
        asyncio.run(campaign_routes.create_draft(_payload(), request))

    assert error.value.status_code == 503
    assert error.value.detail == "draft_create_unavailable"
    assert subscriptions.finish_calls == [{
        "workspace_id": "workspace-a", "reservation_id": reservation_id, "outcome": "consumed",
    }]


def test_successful_draft_is_not_returned_if_quota_finalization_fails(monkeypatch):
    actor_id = str(uuid4())
    reservation_id = str(uuid4())
    subscriptions = _Subscriptions(
        reservations=[{"allowed": True, "reason": "reserved", "status": "reserved",
                       "reservation_id": reservation_id}],
        finish_results=[False],
    )
    store = _CampaignStore(draft={"id": str(uuid4()), "status": "pending_approval"})
    request, _ = _request(subscriptions=subscriptions, campaign_store=store, user_id=actor_id)
    _patch_auth(monkeypatch, actor_id)

    with pytest.raises(HTTPException) as error:
        asyncio.run(campaign_routes.create_draft(_payload(), request))

    assert error.value.status_code == 503
    assert error.value.detail == "draft_quota_persistence_failed"


def test_review_requires_admin_and_only_passes_explicit_human_decision(monkeypatch):
    actor_id = str(uuid4())
    subscriptions = _Subscriptions()
    reviewed = {"id": str(uuid4()), "status": "approved", "reviewed_by": actor_id}
    store = _CampaignStore(review=reviewed)
    request, _ = _request(subscriptions=subscriptions, campaign_store=store, user_id=actor_id)
    _patch_auth(monkeypatch, actor_id)
    payload = campaign_routes.DraftReview(
        workspace_id="workspace-a", decision="approved", note="Reviewed evidence",
    )

    result = asyncio.run(campaign_routes.review_draft(uuid4(), payload, request))

    assert result == reviewed
    assert store.review_calls[0]["decision"] == "approved"
    assert store.review_calls[0]["actor_id"] == actor_id


def test_review_conflict_and_store_failure_are_not_reported_as_success(monkeypatch):
    actor_id = str(uuid4())
    subscriptions = _Subscriptions()
    store = _CampaignStore(review=None)
    request, _ = _request(subscriptions=subscriptions, campaign_store=store, user_id=actor_id)
    _patch_auth(monkeypatch, actor_id)
    payload = campaign_routes.DraftReview(workspace_id="workspace-a", decision="rejected")

    with pytest.raises(HTTPException) as conflict:
        asyncio.run(campaign_routes.review_draft(uuid4(), payload, request))
    assert conflict.value.status_code == 409

    store.review_error = RuntimeError("private DB error")
    with pytest.raises(HTTPException) as unavailable:
        asyncio.run(campaign_routes.review_draft(uuid4(), payload, request))
    assert unavailable.value.status_code == 503
    assert unavailable.value.detail == "draft_review_unavailable"
