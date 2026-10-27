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


@pytest.mark.asyncio
async def test_growth_job_rejects_when_workspace_has_no_quota(monkeypatch):
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
        await workspace_job_routes.enqueue_website_growth_scan(
            payload, request, idempotency_key="test-scan-key-001"
        )

    assert error.value.status_code == 429
    assert subscriptions.reserve_args["feature"] == "website_audits"
    assert subscriptions.finished == []


@pytest.mark.asyncio
async def test_growth_job_consumes_quota_after_queue_acceptance(monkeypatch):
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
    result = await workspace_job_routes.enqueue_website_growth_scan(
        payload, request, idempotency_key="test-scan-key-002"
    )

    assert result["status"] == "queued"
    assert subscriptions.finished == [{
        "workspace_id": "workspace-a",
        "reservation_id": reservation_id,
        "outcome": "consumed",
    }]
