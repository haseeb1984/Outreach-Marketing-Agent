# Browser session and CSRF security foundation

The auth_http_security.py module provides conservative primitives for future browser authentication:
- A __Host-oma_session cookie with Secure, HttpOnly, Path=/ and SameSite=Lax; no Domain attribute is emitted.
- Random CSRF synchronizer tokens and SHA-256 digests for server-side session association.
- Constant-time CSRF digest comparison.
- Exact HTTPS Origin comparison.

These are primitives, not complete CSRF middleware. Before enabling cookie-authenticated state-changing routes:
1. Set the cookie only after successful login and rotate the session identifier after authentication or privilege changes.
2. Store only a CSRF digest or securely associated synchronizer token server-side; never put CSRF tokens in URLs or logs.
3. Require exact configured HTTPS Origin validation and a valid CSRF token on every state-changing request. Review a fallback policy for requests without Origin.
4. Apply authentication rate limits before expensive work and return generic errors.
5. Enforce active workspace membership and role authorization on every resource operation.
6. Add integration tests for browser cookies, CSRF failures, cross-origin attempts, session revocation, and tenant isolation.
7. Do not enable public account or outreach endpoints until these tests and production configuration checks pass.

Production secrets belong in encrypted hosting environment settings. Local secrets belong in ignored .env; only blank placeholders may be committed in .env.example. Never log cookie values, CSRF tokens, Authorization headers, passwords, verification/reset URLs, or raw database/provider exceptions.
