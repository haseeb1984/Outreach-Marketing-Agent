import asyncio

import httpx
import pytest

from app.core.config import settings
from app.services.website_fetch import FetchLimits, fetch_html


async def public_resolver(host: str, port: int) -> list[str]:
    assert host in {"example.com", "www.example.com"}
    return ["93.184.216.34"]


def make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_fetch_html_reads_html_and_checks_resolver():
    async def run():
        async def handler(request):
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<title>Example</title>", request=request)

        async with make_client(handler) as client:
            return await fetch_html("https://example.com/", client=client, resolver=public_resolver)

    result = asyncio.run(run())
    assert result.status_code == 200
    assert result.body == "<title>Example</title>"
    assert result.final_url == "https://example.com/"


def test_fetch_html_rechecks_redirect_destination_before_request():
    async def run():
        requested = []

        async def handler(request):
            requested.append(str(request.url))
            if request.headers.get("host") == "example.com":
                return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"}, request=request)
            raise AssertionError("private redirect must never be requested")

        async def resolver(host: str, port: int) -> list[str]:
            return ["93.184.216.34"]

        async with make_client(handler) as client:
            with pytest.raises(ValueError):
                await fetch_html("https://example.com/", client=client, resolver=resolver)
        assert requested == ["https://93.184.216.34/"]

    asyncio.run(run())


def test_fetch_html_rejects_non_html_and_oversized_content():
    async def run():
        async def non_html(request):
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF", request=request)

        async with make_client(non_html) as client:
            with pytest.raises(ValueError, match="not HTML"):
                await fetch_html("https://example.com/", client=client, resolver=public_resolver)

        async def oversized(request):
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 20, request=request)

        async with make_client(oversized) as client:
            with pytest.raises(ValueError, match="byte limit"):
                await fetch_html("https://example.com/", client=client, limits=FetchLimits(max_bytes=10), resolver=public_resolver)

    asyncio.run(run())


def test_fetch_html_rejects_private_dns_answer_before_request():
    async def run():
        requested = []

        async def handler(request):
            requested.append(request)
            return httpx.Response(200, headers={"content-type": "text/html"}, text="ok", request=request)

        async def private_resolver(host: str, port: int) -> list[str]:
            return ["10.0.0.8"]

        async with make_client(handler) as client:
            with pytest.raises(ValueError, match="non-public"):
                await fetch_html("https://example.com/", client=client, resolver=private_resolver)
        assert requested == []

    asyncio.run(run())



def test_fetch_html_rejects_mixed_public_and_private_dns_answers():
    async def run():
        requested = []

        async def handler(request):
            requested.append(str(request.url))
            return httpx.Response(200, headers={"content-type": "text/html"}, text="ok", request=request)

        async def mixed_resolver(host: str, port: int) -> list[str]:
            return ["93.184.216.34", "192.168.1.10"]

        async with make_client(handler) as client:
            with pytest.raises(ValueError, match="non-public"):
                await fetch_html("https://example.com/", client=client, resolver=mixed_resolver)
        assert requested == []

    asyncio.run(run())


def test_fetch_html_rejects_malformed_dns_answer_before_request():
    async def run():
        requested = []

        async def handler(request):
            requested.append(str(request.url))
            return httpx.Response(200, headers={"content-type": "text/html"}, text="ok", request=request)

        async def malformed_resolver(host: str, port: int) -> list[str]:
            return ["not-an-ip-address"]

        async with make_client(handler) as client:
            with pytest.raises(ValueError, match="invalid IP"):
                await fetch_html("https://example.com/", client=client, resolver=malformed_resolver)
        assert requested == []

    asyncio.run(run())


def test_fetch_html_blocks_public_redirect_outside_allowed_host_scope():
    async def run():
        requested = []

        async def handler(request):
            requested.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://www.example.com/other"}, request=request)

        async def resolver(host: str, port: int) -> list[str]:
            return ["93.184.216.34"]

        async with make_client(handler) as client:
            with pytest.raises(ValueError, match="outside the allowed host scope"):
                await fetch_html(
                    "https://example.com/",
                    client=client,
                    resolver=resolver,
                    allowed_hosts={"example.com"},
                )
        assert requested == ["https://93.184.216.34/"]

    asyncio.run(run())


def test_fetch_html_stops_after_configured_redirect_limit():
    async def run():
        requested = []

        async def handler(request):
            requested.append(str(request.url))
            return httpx.Response(302, headers={"location": "/"}, request=request)

        async with make_client(handler) as client:
            with pytest.raises(ValueError, match="Maximum redirect count"):
                await fetch_html(
                    "https://example.com/",
                    client=client,
                    resolver=public_resolver,
                    limits=FetchLimits(max_redirects=2),
                )
        assert len(requested) == 3

    asyncio.run(run())



def test_fetch_html_rechecks_dns_before_following_same_host_redirect():
    async def run():
        requested = []
        resolutions = 0

        async def handler(request):
            requested.append(str(request.url))
            if request.url.path == "/":
                return httpx.Response(302, headers={"location": "/next"}, request=request)
            return httpx.Response(200, headers={"content-type": "text/html"}, text="unexpected", request=request)

        async def changing_resolver(host: str, port: int) -> list[str]:
            nonlocal resolutions
            resolutions += 1
            if resolutions == 1:
                return ["93.184.216.34"]
            return ["127.0.0.1"]

        async with make_client(handler) as client:
            with pytest.raises(ValueError, match="non-public"):
                await fetch_html("https://example.com/", client=client, resolver=changing_resolver)

        assert resolutions == 2
        assert requested == ["https://93.184.216.34/"]

    asyncio.run(run())


@pytest.mark.parametrize(
    "blocked_address",
    [
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "169.254.169.254",
        "0.0.0.0",
    ],
)
def test_fetch_html_rejects_non_global_ipv4_and_ipv6_answers(blocked_address):
    async def run():
        requested = []

        async def handler(request):
            requested.append(str(request.url))
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="must not be reached",
                request=request,
            )

        async def blocked_resolver(host: str, port: int) -> list[str]:
            return [blocked_address]

        async with make_client(handler) as client:
            with pytest.raises(ValueError, match="non-public"):
                await fetch_html(
                    "https://example.com/",
                    client=client,
                    resolver=blocked_resolver,
                )
        assert requested == []

    asyncio.run(run())


def test_fetch_html_rejects_cross_host_redirect_when_destination_dns_is_private():
    async def run():
        requested = []
        resolutions = []

        async def handler(request):
            requested.append(str(request.url))
            if request.headers.get("host") == "example.com":
                return httpx.Response(
                    302,
                    headers={"location": "https://www.example.com/private"},
                    request=request,
                )
            raise AssertionError("redirect destination with private DNS must never be requested")

        async def changing_resolver(host: str, port: int) -> list[str]:
            resolutions.append((host, port))
            if host == "example.com":
                return ["93.184.216.34"]
            return ["10.0.0.12"]

        async with make_client(handler) as client:
            with pytest.raises(ValueError, match="non-public"):
                await fetch_html(
                    "https://example.com/",
                    client=client,
                    resolver=changing_resolver,
                )

        assert [host for host, _ in resolutions] == ["example.com", "www.example.com"]
        assert requested == ["https://93.184.216.34/"]

    asyncio.run(run())


def test_fetch_html_fails_closed_when_dns_returns_no_addresses():
    async def run():
        requested = []

        async def handler(request):
            requested.append(str(request.url))
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="must not be reached",
                request=request,
            )

        async def empty_resolver(host: str, port: int) -> list[str]:
            return []

        async with make_client(handler) as client:
            with pytest.raises(ValueError, match="no IP addresses"):
                await fetch_html(
                    "https://example.com/",
                    client=client,
                    resolver=empty_resolver,
                )

        assert requested == []

    asyncio.run(run())


def test_production_fetch_pins_validated_ip_and_preserves_host_and_tls_identity(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html"}
        encoding = "utf-8"
        url = httpx.URL("https://93.184.216.34/")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_bytes(self):
            yield b"<title>pinned</title>"

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_options"] = kwargs

        def stream(self, method, url, **kwargs):
            captured["method"] = method
            captured["url"] = str(url)
            captured.update(kwargs)
            return FakeResponse()

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(fetch_html("https://example.com/", resolver=public_resolver))

    assert captured["client_options"]["trust_env"] is False
    assert "proxy" not in captured["client_options"]
    assert captured["method"] == "GET"
    assert captured["url"] == "https://93.184.216.34/"
    assert captured["headers"]["Host"] == "example.com"
    assert captured["headers"]["Connection"] == "close"
    assert captured["extensions"]["sni_hostname"] == "example.com"
    assert captured["follow_redirects"] is False
    assert result.final_url == "https://example.com/"
    assert result.body == "<title>pinned</title>"


def test_production_fetch_rejects_injected_http_client(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")

    async def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text="ok", request=request)

    async def run():
        async with make_client(handler) as client:
            with pytest.raises(ValueError, match="Injected HTTP clients are disabled"):
                await fetch_html("https://example.com/", client=client, resolver=public_resolver)

    asyncio.run(run())


@pytest.mark.parametrize(
    ("url", "address", "expected_url", "expected_host", "expected_sni"),
    [
        (
            "https://example.com/path?q=1",
            "93.184.216.34",
            "https://93.184.216.34/path?q=1",
            "example.com",
            "example.com",
        ),
        (
            "https://example.com:443/path",
            "2001:4860:4860::8888",
            "https://[2001:4860:4860::8888]/path",
            "example.com",
            "example.com",
        ),
        (
            "http://example.com/path",
            "93.184.216.34",
            "http://93.184.216.34/path",
            "example.com",
            None,
        ),
    ],
)
def test_pinned_request_target_preserves_original_http_identity(
    url, address, expected_url, expected_host, expected_sni
):
    from app.services.website_fetch import _pinned_request_target

    pinned_url, headers, extensions = _pinned_request_target(url, address)

    assert pinned_url == expected_url
    assert headers["Host"] == expected_host
    assert extensions.get("sni_hostname") == expected_sni
