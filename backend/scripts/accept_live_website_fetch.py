"""Manual live acceptance for the production website-fetch transport.

Run only from the dedicated GitHub Actions workflow. This makes a real HTTPS
request through fetch_html; it is intentionally not part of the regular test
suite because it depends on an external public service.
"""
from __future__ import annotations

import asyncio
import json

from app.services.website_fetch import fetch_html, resolve_public_addresses


async def main() -> None:
    host = "httpbin.org"
    addresses = await resolve_public_addresses(host, 443)
    if not addresses:
        raise SystemExit("FAIL: no public DNS addresses returned")

    page = await fetch_html(
        "https://httpbin.org/redirect-to?url=%2Fanything&status_code=302",
        allowed_hosts={host},
        allowed_schemes={"https"},
        accepted_content_types={"application/json"},
    )
    if page.status_code != 200:
        raise SystemExit(f"FAIL: unexpected HTTP status {page.status_code}")
    if page.final_url != "https://httpbin.org/anything":
        raise SystemExit(f"FAIL: redirect final URL was {page.final_url!r}")

    try:
        payload = json.loads(page.body)
    except json.JSONDecodeError as exc:
        raise SystemExit("FAIL: HTTPS origin did not return valid JSON") from exc

    echoed_host = payload.get("headers", {}).get("Host", "")
    if echoed_host.lower() != host:
        raise SystemExit(f"FAIL: origin observed Host header {echoed_host!r}")

    print("PASS: real HTTPS request completed through fetch_html")
    print(f"PASS: validated public DNS addresses: {', '.join(addresses)}")
    print(f"PASS: redirect was followed and final URL preserved hostname: {page.final_url}")
    print(f"PASS: origin observed original Host header: {echoed_host}")
    print("PASS: TLS certificate verification succeeded for original hostname")


if __name__ == "__main__":
    asyncio.run(main())
