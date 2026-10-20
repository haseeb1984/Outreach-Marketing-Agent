import asyncio

import httpx
import pytest

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
            if request.url.host == "example.com":
                return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"}, request=request)
            raise AssertionError("private redirect must never be requested")

        async def resolver(host: str, port: int) -> list[str]:
            return ["93.184.216.34"]

        async with make_client(handler) as client:
            with pytest.raises(ValueError):
                await fetch_html("https://example.com/", client=client, resolver=resolver)
        assert requested == ["https://example.com/"]

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
        assert requested == ["https://example.com/"]

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
        assert requested == ["https://example.com/"]

    asyncio.run(run())
