from __future__ import annotations

import pytest

from app.services import paddle_api
from app.services.paddle_api import PaddleAPIError


def test_sandbox_environment_is_default_and_live_requires_explicit_enablement():
    assert paddle_api.paddle_api_base("sandbox", False) == "https://sandbox-api.paddle.com"
    with pytest.raises(PaddleAPIError, match="live_checkout_disabled"):
        paddle_api.paddle_api_base("live", False)
    assert paddle_api.paddle_api_base("live", True) == "https://api.paddle.com"


@pytest.mark.parametrize("url", [
    "http://checkout.paddle.com/txn",
    "https://evil.example/checkout",
    "https://user:pass@checkout.paddle.com/checkout",
    "javascript:alert(1)",
    "",
])
def test_checkout_url_validation_rejects_untrusted_redirects(url):
    with pytest.raises(PaddleAPIError):
        paddle_api._safe_checkout_url(url)


def test_checkout_url_validation_accepts_https_paddle_host():
    assert paddle_api._safe_checkout_url("https://checkout.paddle.com/checkout/txn_123") == "https://checkout.paddle.com/checkout/txn_123"


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    response = None
    calls = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


@pytest.mark.asyncio
async def test_checkout_uses_server_mapped_price_and_workspace_metadata(monkeypatch):
    _Client.calls = []
    _Client.response = _Response(201, {
        "data": {
            "id": "txn_123",
            "checkout": {"url": "https://checkout.paddle.com/checkout/txn_123"},
        }
    })
    monkeypatch.setattr(paddle_api.httpx, "AsyncClient", _Client)
    result = await paddle_api.create_checkout_transaction(
        api_key="secret",
        environment="sandbox",
        live_enabled=False,
        price_id="pri_starter",
        workspace_id="workspace-1",
        plan_slug="starter",
    )
    assert result["transaction_id"] == "txn_123"
    url, kwargs = _Client.calls[0]
    assert url == "https://sandbox-api.paddle.com/transactions"
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert kwargs["json"]["items"] == [{"price_id": "pri_starter", "quantity": 1}]
    assert kwargs["json"]["custom_data"]["workspace_id"] == "workspace-1"


@pytest.mark.asyncio
async def test_provider_error_is_sanitized(monkeypatch):
    _Client.response = _Response(401, {"error": {"detail": "secret account details"}})
    monkeypatch.setattr(paddle_api.httpx, "AsyncClient", _Client)
    with pytest.raises(PaddleAPIError, match="paddle_transaction_request_failed") as error:
        await paddle_api.create_checkout_transaction(
            api_key="secret",
            environment="sandbox",
            live_enabled=False,
            price_id="pri_starter",
            workspace_id="workspace-1",
            plan_slug="starter",
        )
    assert "secret account details" not in str(error.value)


@pytest.mark.asyncio
async def test_customer_portal_returns_only_validated_provider_url(monkeypatch):
    _Client.response = _Response(200, {
        "data": {"urls": {"general": {"overview": "https://customer-portal.paddle.com/session"}}}
    })
    monkeypatch.setattr(paddle_api.httpx, "AsyncClient", _Client)
    url = await paddle_api.create_customer_portal_session(
        api_key="secret", environment="sandbox", live_enabled=False, customer_id="ctm_123"
    )
    assert url == "https://customer-portal.paddle.com/session"
