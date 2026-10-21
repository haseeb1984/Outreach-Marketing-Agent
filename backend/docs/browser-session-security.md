# Browser session and CSRF security

The authentication router uses a __Host-oma_session cookie with Secure, HttpOnly, Path=/ and SameSite=Lax, plus a separate __Host-oma_csrf cookie. The server stores only the session token digest and CSRF token digest. State-changing authenticated routes require exact configured HTTPS Origin matching and a valid X-CSRF-Token header. Login and session rotation issue fresh session and CSRF values; logout revokes the server session and clears both cookies.

Verification and reset landing pages set Referrer-Policy: no-referrer and Cache-Control: no-store. Token-consuming actions use POST so link scanners do not automatically consume one-time tokens. Reset tokens are submitted through a hidden form field, not interpolated into JavaScript source.

## Deployment checks

- Configure PUBLIC_BASE_URL as the exact public HTTPS origin.
- Use a unique high-entropy SECRET_KEY (at least 32 bytes) for keyed rate-limit identifiers.
- Apply migrations before enabling routes. The app intentionally does not migrate the database during startup.
- Test session rotation/revocation, CSRF failures, cross-origin requests, reset expiry/reuse, and rate-limit failures.
- Enforce workspace membership and role checks on every private resource route. Authentication alone is not tenant authorization.
- Never log passwords, cookies, CSRF values, verification/reset tokens, provider credentials, or raw provider/database exceptions.
