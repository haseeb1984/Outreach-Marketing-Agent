# Authentication persistence adapter

AuthStore provides PostgreSQL-backed registration, single-use email verification, password authentication, session creation/rotation/revocation, password reset, and workspace membership checks. Registration atomically creates a pending user, personal workspace, owner membership, and hashed verification-token record. Session and reset tokens are returned only to trusted server code; only digests are stored.

The FastAPI authentication router is wired under /api/v1/auth. It adds HTTPS-origin checks, secure host-only cookies, CSRF validation on authenticated state-changing requests, database-backed rate limiting, generic responses for account-dependent registration/reset operations, and sanitized SMTP failures.

## Operational constraints

- Apply migrations explicitly; API startup does not run SQL migrations.
- Routes fail closed if the database/rate limiter is not configured. Rate limiting requires a secret key of at least 32 bytes.
- SMTP delivery requires HTTPS PUBLIC_BASE_URL and configured STARTTLS credentials.
- Every future private workspace endpoint must derive identity from the server-authenticated session and verify active workspace membership before reading or changing tenant resources.
- This phase does not implement a complete dashboard, billing, real outreach delivery, reply synchronization, or production deployment verification.
