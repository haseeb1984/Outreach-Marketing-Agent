"""Minimal Paddle Billing API client with strict environment and URL validation."""
from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx


class PaddleAPIError(RuntimeError):
    """A provider request failed without exposing provider response details."""


def paddle_api_base(environment: str, live_enabled: bool) -> str:
    if environment == "sandbox":
        return "https://sandbox-api.paddle.com"
    if environment in {"live", "production"}:
        if not live_enabled:
            raise PaddleAPIError("live_checkout_disabled")
        return "https://api.paddle.com"
    raise PaddleAPIError("invalid_paddle_environment")


def _safe_checkout_url(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise PaddleAPIError("checkout_url_missing")
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or not (hostname.endswith(".paddle.com") or hostname.endswith(".paddle.io"))
        ):
            raise PaddleAPIError("checkout_url_invalid")
    except ValueError:
        raise PaddleAPIError("checkout_url_invalid") from None
    return value


async def create_checkout_transaction(
    *,
    api_key: str,
    environment: str,
    live_enabled: bool,
    price_id: str,
    workspace_id: str,
    plan_slug: str,
) -> dict[str, str]:
    if not api_key or not price_id or not workspace_id or not plan_slug:
        raise PaddleAPIError("paddle_checkout_not_configured")
    base = paddle_api_base(environment, live_enabled)
    payload = {
        "items": [{"price_id": price_id, "quantity": 1}],
        "collection_mode": "automatic",
        "custom_data": {"workspace_id": workspace_id, "plan_slug": plan_slug},
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{base}/transactions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code not in {200, 201}:
            raise PaddleAPIError("paddle_transaction_request_failed")
        body = response.json()
    except PaddleAPIError:
        raise
    except Exception:
        raise PaddleAPIError("paddle_transaction_request_failed") from None
    data = body.get("data") if isinstance(body, Mapping) else None
    if not isinstance(data, Mapping):
        raise PaddleAPIError("paddle_transaction_response_invalid")
    transaction_id = data.get("id")
    checkout = data.get("checkout")
    checkout_url = checkout.get("url") if isinstance(checkout, Mapping) else None
    if not isinstance(transaction_id, str) or not transaction_id.startswith("txn_"):
        raise PaddleAPIError("paddle_transaction_response_invalid")
    return {"transaction_id": transaction_id, "checkout_url": _safe_checkout_url(checkout_url)}


async def create_customer_portal_session(
    *,
    api_key: str,
    environment: str,
    live_enabled: bool,
    customer_id: str,
) -> str:
    if not api_key or not isinstance(customer_id, str) or not customer_id.startswith("ctm_"):
        raise PaddleAPIError("paddle_customer_not_configured")
    base = paddle_api_base(environment, live_enabled)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{base}/customers/{customer_id}/portal-sessions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={},
            )
        if response.status_code not in {200, 201}:
            raise PaddleAPIError("paddle_portal_request_failed")
        body = response.json()
    except PaddleAPIError:
        raise
    except Exception:
        raise PaddleAPIError("paddle_portal_request_failed") from None
    data = body.get("data") if isinstance(body, Mapping) else None
    urls = data.get("urls") if isinstance(data, Mapping) else None
    general = urls.get("general") if isinstance(urls, Mapping) else None
    overview = general.get("overview") if isinstance(general, Mapping) else None
    return _safe_checkout_url(overview)
