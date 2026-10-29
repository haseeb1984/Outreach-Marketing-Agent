import asyncio
import pytest
from pydantic import ValidationError

from app.api.workspace_job_routes import WebsiteGrowthScanRequest, _normalize_start_url


def test_growth_scan_request_normalizes_url_and_deduplicates_queries():
    payload = WebsiteGrowthScanRequest(
        workspace_id="workspace-a",
        start_url="https://example.com/growth?token=do-not-store#section",
        business_type="  SaaS  ",
        target_market="  United States  ",
        target_queries=[" CRM software ", "CRM software", "marketing automation"],
    )

    assert payload.start_url == "https://example.com/growth"
    assert payload.business_type == "SaaS"
    assert payload.target_market == "United States"
    assert payload.target_queries == ["CRM software", "marketing automation"]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:password@example.com/",
        "https://example.com:8443/",
        "javascript:alert(1)",
        "https:///missing-host",
    ],
)
def test_growth_scan_rejects_unsafe_website_urls(url):
    with pytest.raises((ValueError, ValidationError)):
        _normalize_start_url(url)


def test_growth_scan_requires_workspace_and_bounded_inputs():
    with pytest.raises(ValidationError):
        WebsiteGrowthScanRequest(
            workspace_id="",
            start_url="https://example.com",
            business_type="SaaS",
            target_market="US",
            max_pages=11,
        )


def test_growth_scan_does_not_accept_boolean_page_limits():
    with pytest.raises(ValidationError):
        WebsiteGrowthScanRequest(
            workspace_id="workspace-a",
            start_url="https://example.com",
            business_type="SaaS",
            target_market="US",
            max_pages=True,
        )


def test_growth_scan_rejects_empty_queries():
    with pytest.raises(ValidationError):
        WebsiteGrowthScanRequest(
            workspace_id="workspace-a",
            start_url="https://example.com",
            business_type="SaaS",
            target_market="US",
            target_queries=["valid query", "   "],
        )


from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from starlette.requests import Request

from app.api import workspace_job_routes


class _DomainStore:
    async def authorize_url(self, *, workspace_id, url):
        return {"authorized": True}


class _SubscriptionStore:
    def __init__(self, reservation):
        self.reservation = reservation
        self.finished = []

    async def reserve_usage(self, **kwargs):
        self.reserve_args = kwargs
        return self.reservation

    async def finish_reservation(self, **kwargs):
        self.finished.append(kwargs)
        return True


def _request_with_state(**state_values):
    app = FastAPI()
    for key, value in state_values.items():
        setattr(app.state, key, value)
    return Request({"type": "http", "app": app, "method": "POST", "path": "/", "headers": [], "query_string": b""})


def test_growth_job_rejects_when_workspace_has_no_quota(monkeypatch):
    subscriptions = _SubscriptionStore({"allowed": False, "reason": "quota_exhausted"})
    request = _request_with_state(
        domain_authorization_store=_DomainStore(),
        subscription_store=subscriptions,
        db_pool=object(),
    )

    async def authenticated(_request):
        return None, None, {"user_id": str(uuid4())}

    async def authorize(*args, **kwargs):
        return None

    monkeypatch.setattr(workspace_job_routes, "_authenticated", authenticated)
    monkeypatch.setattr(workspace_job_routes, "_check_csrf", lambda *_args: None)
    monkeypatch.setattr(workspace_job_routes, "_authorize", authorize)

    payload = WebsiteGrowthScanRequest(
        workspace_id="workspace-a",
        start_url="https://example.com/",
        business_type="SaaS",
        target_market="US",
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(workspace_job_routes.enqueue_website_growth_scan(
            payload, request, idempotency_key="test-scan-key-001"
        ))

    assert error.value.status_code == 429
    assert subscriptions.reserve_args["feature"] == "website_audits"
    assert subscriptions.finished == []


def test_growth_job_consumes_quota_after_queue_acceptance(monkeypatch):
    reservation_id = str(uuid4())
    subscriptions = _SubscriptionStore({
        "allowed": True,
        "reason": "reserved",
        "status": "reserved",
        "reservation_id": reservation_id,
    })
    request = _request_with_state(
        domain_authorization_store=_DomainStore(),
        subscription_store=subscriptions,
        db_pool=object(),
    )

    async def authenticated(_request):
        return None, None, {"user_id": str(uuid4())}

    async def authorize(*args, **kwargs):
        return None

    class _Queue:
        def __init__(self, _pool):
            pass

        async def enqueue(self, **kwargs):
            return {
                "id": str(uuid4()),
                "workspace_id": kwargs["workspace_id"],
                "job_type": kwargs["job_type"],
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": 3,
                "run_after": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc),
            }

    monkeypatch.setattr(workspace_job_routes, "_authenticated", authenticated)
    monkeypatch.setattr(workspace_job_routes, "_check_csrf", lambda *_args: None)
    monkeypatch.setattr(workspace_job_routes, "_authorize", authorize)
    monkeypatch.setattr(workspace_job_routes, "WorkspaceJobQueue", _Queue)

    payload = WebsiteGrowthScanRequest(
        workspace_id="workspace-a",
        start_url="https://example.com/",
        business_type="SaaS",
        target_market="US",
    )
    result = asyncio.run(workspace_job_routes.enqueue_website_growth_scan(
        payload, request, idempotency_key="test-scan-key-002"
    ))

    assert result["status"] == "queued"
    assert subscriptions.finished == [{
        "workspace_id": "workspace-a",
        "reservation_id": reservation_id,
        "outcome": "consumed",
    }]



def test_growth_job_idempotent_retry_returns_existing_job_after_quota_consumed(monkeypatch):
    reservation_id = str(uuid4())
    subscriptions = _SubscriptionStore({
        "allowed": True,
        "reason": "idempotent_replay",
        "status": "consumed",
        "reservation_id": reservation_id,
    })
    request = _request_with_state(
        domain_authorization_store=_DomainStore(),
        subscription_store=subscriptions,
        db_pool=object(),
    )

    async def authenticated(_request):
        return None, None, {"user_id": str(uuid4())}

    async def authorize(*args, **kwargs):
        return None

    existing_job_id = str(uuid4())

    class _Queue:
        def __init__(self, _pool):
            pass

        async def enqueue(self, **kwargs):
            assert kwargs["idempotency_key"] == "test-scan-key-003"
            assert kwargs["payload"]["usage_reservation_id"] == reservation_id
            return {
                "id": existing_job_id,
                "workspace_id": kwargs["workspace_id"],
                "job_type": kwargs["job_type"],
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": 3,
                "run_after": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc),
            }

    monkeypatch.setattr(workspace_job_routes, "_authenticated", authenticated)
    monkeypatch.setattr(workspace_job_routes, "_check_csrf", lambda *_args: None)
    monkeypatch.setattr(workspace_job_routes, "_authorize", authorize)
    monkeypatch.setattr(workspace_job_routes, "WorkspaceJobQueue", _Queue)

    payload = WebsiteGrowthScanRequest(
        workspace_id="workspace-a",
        start_url="https://example.com/",
        business_type="SaaS",
        target_market="US",
    )
    result = asyncio.run(workspace_job_routes.enqueue_website_growth_scan(
        payload, request, idempotency_key="test-scan-key-003"
    ))

    assert result["id"] == existing_job_id
    assert result["status"] == "queued"
    assert subscriptions.finished == []


def test_growth_job_preserves_reservation_when_enqueue_outcome_is_ambiguous(monkeypatch):
    reservation_id = str(uuid4())
    subscriptions = _SubscriptionStore({
        "allowed": True,
        "reason": "reserved",
        "status": "reserved",
        "reservation_id": reservation_id,
    })
    request = _request_with_state(
        domain_authorization_store=_DomainStore(),
        subscription_store=subscriptions,
        db_pool=object(),
    )

    async def authenticated(_request):
        return None, None, {"user_id": str(uuid4())}

    async def authorize(*args, **kwargs):
        return None

    class _AmbiguousQueue:
        def __init__(self, _pool):
            pass

        async def enqueue(self, **kwargs):
            # Simulate a database commit followed by a lost response.
            raise RuntimeError("connection lost after commit")

    monkeypatch.setattr(workspace_job_routes, "_authenticated", authenticated)
    monkeypatch.setattr(workspace_job_routes, "_check_csrf", lambda *_args: None)
    monkeypatch.setattr(workspace_job_routes, "_authorize", authorize)
    monkeypatch.setattr(workspace_job_routes, "WorkspaceJobQueue", _AmbiguousQueue)

    payload = WebsiteGrowthScanRequest(
        workspace_id="workspace-a",
        start_url="https://example.com/",
        business_type="SaaS",
        target_market="US",
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(workspace_job_routes.enqueue_website_growth_scan(
            payload, request, idempotency_key="test-scan-ambiguous-001"
        ))

    assert error.value.status_code == 503
    assert error.value.detail == "website_growth_job_unavailable"
    # Releasing here could orphan a job that committed despite the lost response.
    assert subscriptions.finished == []


def test_growth_job_returns_conflict_for_reused_idempotency_key_with_different_payload(monkeypatch):
    reservation_id = str(uuid4())
    subscriptions = _SubscriptionStore({
        "allowed": True,
        "reason": "idempotent_replay",
        "status": "reserved",
        "reservation_id": reservation_id,
    })
    request = _request_with_state(
        domain_authorization_store=_DomainStore(),
        subscription_store=subscriptions,
        db_pool=object(),
    )

    async def authenticated(_request):
        return None, None, {"user_id": str(uuid4())}

    async def authorize(*args, **kwargs):
        return None

    class _ConflictingQueue:
        def __init__(self, _pool):
            pass

        async def enqueue(self, **kwargs):
            raise ValueError("idempotency_key_conflict")

    monkeypatch.setattr(workspace_job_routes, "_authenticated", authenticated)
    monkeypatch.setattr(workspace_job_routes, "_check_csrf", lambda *_args: None)
    monkeypatch.setattr(workspace_job_routes, "_authorize", authorize)
    monkeypatch.setattr(workspace_job_routes, "WorkspaceJobQueue", _ConflictingQueue)

    payload = WebsiteGrowthScanRequest(
        workspace_id="workspace-a",
        start_url="https://example.com/changed",
        business_type="SaaS",
        target_market="US",
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(workspace_job_routes.enqueue_website_growth_scan(
            payload, request, idempotency_key="test-scan-conflict-001"
        ))

    assert error.value.status_code == 409
    assert error.value.detail == "idempotency_key_conflict"
    assert subscriptions.finished == []
