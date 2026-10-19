"""Bounded HTTP retrieval primitives for the read-only website audit.

This service manually follows redirects and checks DNS answers before each request.
For hostile multi-tenant production traffic, deploy behind an egress proxy that
pins validated destination IPs to the actual connection; a separate DNS lookup
cannot by itself eliminate DNS-rebinding races in a generic HTTP client.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import urljoin, urlsplit

import httpx

from app.services.website_audit import validate_page_url


Resolver = Callable[[str, int], Awaitable[list[str]]]


@dataclass(frozen=True)
class FetchLimits:
    timeout_seconds: float = 8.0
    max_redirects: int = 3
    max_bytes: int = 1_000_000


@dataclass(frozen=True)
class FetchedPage:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: str


async def resolve_public_addresses(host: str, port: int) -> list[str]:
    """Resolve all A/AAAA answers and reject the host if any answer is non-public."""
    loop = asyncio.get_running_loop()
    try:
        records = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror) as exc:
        raise ValueError("Hostname could not be resolved") from exc
    addresses = sorted({record[4][0].split("%", 1)[0] for record in records})
    if not addresses:
        raise ValueError("Hostname returned no IP addresses")
    for raw in addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise ValueError("DNS returned an invalid IP address") from exc
        if not address.is_global:
            raise ValueError("Hostname resolves to a non-public IP address")
    return addresses


async def fetch_html(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    limits: FetchLimits = FetchLimits(),
    resolver: Resolver = resolve_public_addresses,
    allowed_hosts: set[str] | None = None,
) -> FetchedPage:
    """Fetch a single HTML page with bounded redirects and response size.

    Injected clients are useful for tests. Production callers should use the default
    client or a vetted transport/egress proxy, never a client with redirect following
    enabled. Only HTML/XHTML is returned; compressed payload size is bounded while
    streaming through httpx's decoded byte iterator.
    """
    requested_url = validate_page_url(url)
    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(limits.timeout_seconds),
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "OutreachMarketingAgentAudit/0.1 (+read-only; bounded-fetch)"},
    )
    current_url = requested_url
    try:
        for redirect_count in range(limits.max_redirects + 1):
            current_url = validate_page_url(current_url)
            parsed = urlsplit(current_url)
            host = (parsed.hostname or "").lower().rstrip(".")
            if allowed_hosts is not None and host not in {item.lower().rstrip(".") for item in allowed_hosts}:
                raise ValueError("Request host is outside the allowed host scope")
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
            addresses = await resolver(host, port)
            if not addresses:
                raise ValueError("Hostname returned no IP addresses")
            for raw_address in addresses:
                try:
                    resolved_ip = ipaddress.ip_address(raw_address.split("%", 1)[0])
                except ValueError as exc:
                    raise ValueError("DNS returned an invalid IP address") from exc
                if not resolved_ip.is_global:
                    raise ValueError("Hostname resolves to a non-public IP address")
            async with active_client.stream("GET", current_url, follow_redirects=False) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect response has no Location header")
                    if redirect_count >= limits.max_redirects:
                        raise ValueError("Maximum redirect count exceeded")
                    current_url = urljoin(current_url, location)
                    # Validate destination and scope before any request to it.
                    validate_page_url(current_url)
                    destination_host = (urlsplit(current_url).hostname or "").lower().rstrip(".")
                    if allowed_hosts is not None and destination_host not in {item.lower().rstrip(".") for item in allowed_hosts}:
                        raise ValueError("Redirect destination is outside the allowed host scope")
                    continue
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise ValueError("Target response is not HTML")
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > limits.max_bytes:
                            raise ValueError("Response exceeds the configured byte limit")
                    except ValueError as exc:
                        if str(exc) == "Response exceeds the configured byte limit":
                            raise
                        raise ValueError("Invalid Content-Length header") from exc
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > limits.max_bytes:
                        raise ValueError("Response exceeds the configured byte limit")
                    chunks.append(chunk)
                encoding = response.encoding or "utf-8"
                try:
                    body = b"".join(chunks).decode(encoding, errors="replace")
                except LookupError:
                    body = b"".join(chunks).decode("utf-8", errors="replace")
                return FetchedPage(
                    requested_url=requested_url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=content_type,
                    body=body,
                )
        raise ValueError("Maximum redirect count exceeded")
    except httpx.TimeoutException as exc:
        raise ValueError("Website request timed out") from exc
    except httpx.HTTPError as exc:
        raise ValueError("Website request failed") from exc
    finally:
        if owns_client:
            await active_client.aclose()
