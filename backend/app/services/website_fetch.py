"""Bounded HTTP retrieval with connection-pinned DNS for the read-only website audit.

Each request connects to a previously validated IP literal while preserving the
original Host header and TLS SNI/certificate hostname. Redirects are handled
manually and independently resolved/pinned before the next connection.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.core.config import settings
from app.services.website_audit import validate_page_url


Resolver = Callable[[str, int], Awaitable[list[str]]]


def validate_fetch_configuration() -> None:
    """Validate static fetch safety configuration.

    Outbound requests are pinned to validated public IP addresses at connection
    time, so production does not require a separately provisioned egress proxy
    or proxy secret. Keep this callable for API/worker startup and readiness
    checks; there is no environment-dependent proxy configuration to validate.
    """
    return None


def _pinned_request_target(url: str, address: str) -> tuple[str, dict[str, str], dict[str, str]]:
    """Return an IP-literal URL plus original Host and TLS SNI identity."""
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        hostname = hostname.encode("idna").decode("ascii")
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    pinned_host = f"[{ip.compressed}]" if ip.version == 6 else ip.compressed
    original_host = f"[{hostname}]" if ":" in hostname else hostname
    port = parsed.port
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    pinned_netloc = pinned_host if port in {None, default_port} else f"{pinned_host}:{port}"
    host_header = original_host if port in {None, default_port} else f"{original_host}:{port}"
    pinned_url = urlunsplit((parsed.scheme, pinned_netloc, parsed.path or "/", parsed.query, ""))
    # Do not reuse an IP-keyed pooled TLS connection for a different hostname.
    headers = {"Host": host_header, "Connection": "close"}
    extensions = {"sni_hostname": hostname} if parsed.scheme.lower() == "https" else {}
    return pinned_url, headers, extensions


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
    addresses = sorted({record[4][0].split("%", 1)[0] for record in records}, key=lambda address: (":" in address, address))
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
    allowed_schemes: set[str] | None = None,
    accepted_content_types: set[str] | None = None,
) -> FetchedPage:
    """Fetch a single HTML page with bounded redirects and response size.

    By default only HTML/XHTML is accepted. Trusted callers may pass a narrow set
    of additional content types for robots.txt or XML sitemap documents.

    Injected clients are useful for tests; production callers use the default client.
    Every request targets a validated IP literal, with the original Host and TLS
    SNI identity retained. Only HTML/XHTML is returned; decoded response bytes are
    bounded while streaming through httpx's byte iterator.
    """
    if (
        not isinstance(limits.timeout_seconds, (int, float))
        or limits.timeout_seconds <= 0
        or not isinstance(limits.max_redirects, int)
        or limits.max_redirects < 0
        or not isinstance(limits.max_bytes, int)
        or limits.max_bytes <= 0
    ):
        raise ValueError("Fetch limits must specify a positive timeout and byte limit and a non-negative redirect limit")

    requested_url = validate_page_url(url)
    owns_client = client is None
    is_production = settings.environment.strip().lower() == "production"
    if is_production and client is not None:
        raise ValueError("Injected HTTP clients are disabled in production")
    active_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(limits.timeout_seconds),
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "OutreachMarketingAgentAudit/0.1 (+read-only; bounded-fetch)"},
    )
    current_url = requested_url
    try:
        try:
            async with asyncio.timeout(limits.timeout_seconds):
                for redirect_count in range(limits.max_redirects + 1):
                    current_url = validate_page_url(current_url)
                    parsed = urlsplit(current_url)
                    scheme = parsed.scheme.lower()
                    if allowed_schemes is not None and scheme not in {item.lower() for item in allowed_schemes}:
                        raise ValueError("Request scheme is outside the allowed scheme scope")
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
                    # Connect to the exact address we just validated. The original hostname
                    # remains the HTTP Host and TLS SNI/certificate identity.
                    pinned_url, request_headers, request_extensions = _pinned_request_target(
                        current_url, addresses[0]
                    )
                    async with active_client.stream(
                        "GET",
                        pinned_url,
                        headers=request_headers,
                        extensions=request_extensions,
                        follow_redirects=False,
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise ValueError("Redirect response has no Location header")
                            if redirect_count >= limits.max_redirects:
                                raise ValueError("Maximum redirect count exceeded")
                            current_url = urljoin(current_url, location)
                            # Validate destination and scope before any request to it.
                            validate_page_url(current_url)
                            destination = urlsplit(current_url)
                            if allowed_schemes is not None and destination.scheme.lower() not in {item.lower() for item in allowed_schemes}:
                                raise ValueError("Redirect destination is outside the allowed scheme scope")
                            destination_host = (destination.hostname or "").lower().rstrip(".")
                            if allowed_hosts is not None and destination_host not in {item.lower().rstrip(".") for item in allowed_hosts}:
                                raise ValueError("Redirect destination is outside the allowed host scope")
                            continue
                        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        permitted_types = accepted_content_types or {"text/html", "application/xhtml+xml"}
                        if 200 <= response.status_code < 300 and content_type not in permitted_types:
                            if accepted_content_types is None:
                                raise ValueError("Target response is not HTML")
                            raise ValueError("Target response content type is not permitted")
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
                            final_url=current_url,
                            status_code=response.status_code,
                            content_type=content_type,
                            body=body,
                        )
                raise ValueError("Maximum redirect count exceeded")
        except TimeoutError as exc:
            raise ValueError("Website request timed out") from exc
    except httpx.TimeoutException as exc:
        raise ValueError("Website request timed out") from exc
    except httpx.HTTPError as exc:
        raise ValueError("Website request failed") from exc
    finally:
        if owns_client:
            await active_client.aclose()


async def fetch_text_document(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    limits: FetchLimits = FetchLimits(max_bytes=500_000),
    resolver: Resolver = resolve_public_addresses,
    allowed_hosts: set[str] | None = None,
    allowed_schemes: set[str] | None = None,
    accepted_content_types: set[str] | None = None,
) -> FetchedPage:
    """Fetch a bounded text/XML document through the same SSRF and redirect guards."""
    permitted = accepted_content_types or {
        "text/plain",
        "application/xml",
        "text/xml",
        "application/rss+xml",
        "application/atom+xml",
    }
    return await fetch_html(
        url,
        client=client,
        limits=limits,
        resolver=resolver,
        allowed_hosts=allowed_hosts,
        allowed_schemes=allowed_schemes,
        accepted_content_types=permitted,
    )
