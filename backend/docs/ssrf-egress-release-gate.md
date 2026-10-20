# SSRF Egress Security Release Gate

## Status

**Release-blocking requirement.** The current website fetcher validates URLs and DNS answers, checks again before redirects, restricts redirects, and has adversarial tests. These controls reduce risk but do **not** prevent DNS rebinding at the connection layer: a hostname can resolve differently between validation and the HTTP client's socket connection.

Do not expose website crawl, audit, or job-enqueue functionality to untrusted/public callers until every mandatory gate below is implemented, tested, and reviewed.

## Mandatory production controls

### 1. Enforce destination policy at connection time

Use one of these designs:

- A dedicated, trusted egress proxy that resolves hostnames and enforces the destination-IP policy at the moment it opens the upstream connection; or
- A custom transport/connector that pins the socket to an IP address from the validated DNS result while preserving the original hostname for TLS SNI, certificate verification, and the HTTP Host header.

Do not treat a preflight DNS lookup followed by an ordinary hostname-based HTTP connection as sufficient. Do not silently trust ambient proxy environment variables. If a proxy is part of the security boundary, configure it explicitly and fail closed when it is unavailable or misconfigured.

The fetcher now reads `TRUSTED_EGRESS_PROXY_URL` from environment-backed settings and refuses production fetches when it is unset; it also rejects injected HTTP clients in production so callers cannot silently bypass that configured proxy. The configured proxy must be operator-managed and must enforce destination-IP policy at connection time. This application guard is not proof that the proxy itself is secure; deployment must supply and integration-test the trusted proxy before public crawling is enabled.

### 2. URL and destination restrictions

For every initial URL and redirect hop:

- Permit only explicitly supported HTTP(S) schemes; production policy may require HTTPS.
- Reject URL user information, malformed hostnames, unsupported ports, and ambiguous or invalid IP literals.
- Resolve all candidate A/AAAA addresses and reject the destination if any candidate is non-public or cannot be classified safely.
- Block loopback, private, link-local, multicast, reserved, unspecified, IPv4-mapped IPv6, and cloud/container metadata destinations, including IPv6 equivalents.
- Enforce the same destination policy against the IP actually used for the socket connection, not just the hostname's earlier DNS response.
- Do not follow redirects automatically. Revalidate destination policy and host scope for each hop before opening the next connection.

### 3. Bound resource use and response handling

- Keep strict connection/read timeouts, redirect caps, response-byte caps, page-count/depth caps, and concurrency limits.
- Accept only expected content types for each feature; do not execute fetched scripts or render untrusted active content in a privileged browser context.
- Apply robots and domain-verification policy as separate controls; neither is an SSRF defense.
- Do not log full URLs, query strings, authorization headers, cookies, response bodies, or exception details that may contain user-supplied secrets. Emit safe error codes and correlation IDs only.

### 4. Workspace and job authorization

- Public callers must never choose an arbitrary `workspace_id` and thereby gain access to that workspace.
- Derive workspace identity from a validated authenticated session and verify the user's membership/role on every scoped read, write, domain operation, and enqueue action.
- Workers must take workspace identity from the trusted persisted job record, not from an untrusted payload.
- Keep enqueue and worker execution unavailable to unauthenticated callers until authentication, CSRF/session protections where applicable, rate limits, quotas, and audit events are wired into the routes.
- Require human approval for external outreach, publishing, spending, and other consequential actions.

## Required adversarial test coverage

Before release, automated tests must demonstrate:

- Mixed public and private DNS answers fail closed before an upstream request.
- Malformed, empty, or unclassifiable DNS answers fail closed.
- DNS rebinding between validation and connection cannot reach a private or metadata IP.
- Redirects to a private IP, another disallowed host, a different scheme, or a disallowed port are blocked before the connection.
- Same-host redirect DNS changes are blocked at connection time, not merely caught by a test resolver call.
- IPv4, IPv6, IPv4-mapped IPv6, loopback, link-local, reserved, and metadata-address cases are covered.
- Redirect, byte, timeout, page-count, and concurrency limits are enforced.
- A user cannot access another workspace's domains, jobs, or results by altering IDs or payloads.
- Failure logs and client responses contain no credential canaries, full query strings, cookies, tokens, or connection strings.

Tests that mock a resolver are useful unit tests, but they do not replace transport/proxy integration tests proving which IP receives the actual connection. Include at least one integration test against the real configured egress boundary.

## Release checklist

A release owner must record evidence for each item:

- [ ] Egress architecture selected and documented.
- [ ] Connection-time IP enforcement implemented and reviewed.
- [ ] Proxy/transport configuration fails closed and cannot be bypassed by ambient environment settings.
- [ ] Adversarial unit and integration tests pass in CI.
- [ ] Workspace authorization and rate/quotas are enforced on every exposed operation.
- [ ] Secret-safe logs and generic external errors verified.
- [ ] Production-like tests confirm metadata/private destinations are unreachable.
- [ ] Security review and explicit release approval recorded.

Until all boxes are verified, keep public crawler/audit/enqueue endpoints disabled. Passing the current unit tests alone is not production authorization.
