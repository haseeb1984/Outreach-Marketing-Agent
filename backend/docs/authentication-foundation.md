# Authentication and workspace security foundation

Migrations `003_authentication_foundation.sql` and `004_auth_rate_limits.sql` add tables for users, workspace memberships, revocable sessions, email verification, password reset, security audit events, and keyed rate-limit buckets. The `auth_security.py` module provides bounded password hashing, email normalization, and opaque-token digest primitives. The `auth_rate_limiter.py` module atomically increments PostgreSQL fixed-window buckets while storing only an HMAC digest of a namespaced identifier. Password authentication now performs a scrypt verification against a precomputed dummy hash when no active, verified account is found, reducing account-state timing differences. This does not replace route-level rate limiting.

## HTTP authentication foundation (not released)

The feature branch now includes HTTP routes for `POST /api/v1/auth/register`, `POST /api/v1/auth/verify-email`, `GET /api/v1/auth/verify-email` (confirmation page only), `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `POST /api/v1/auth/rotate`, and `POST /api/v1/auth/logout`. These routes are not a production release: they fail closed unless a database, a `SECRET_KEY` of at least 32 bytes, an HTTPS `PUBLIC_BASE_URL`, and required SMTP configuration are present. Vercel deployment remains on hold.

Implemented controls:
- Registration creates a pending account and sends a single-use verification email; duplicate registration returns a generic response. The verification landing page only consumes the token after an explicit POST, reducing link-scanner activation.
- Login, registration and verification use independent database-backed IP/account rate-limit buckets. Client IP is taken from the direct connection; forwarded headers are intentionally not trusted.
- Session cookies are Secure, HttpOnly, host-only `__Host-` cookies. A separate Secure host-only CSRF cookie is readable by the browser client; unsafe authenticated requests must also send its value in `X-CSRF-Token`, which is checked against the digest stored for the current session, and pass exact HTTPS Origin validation.
- Session rotation atomically revokes the previous session and issues a fresh session and CSRF token. Logout validates Origin and CSRF before revoking the session. Authentication responses are marked no-store.
- HTTP-level regression tests cover login cookies, session lookup, logout revocation, Origin enforcement, CSRF checks, and verification-page behavior.

Still incomplete before production use:
1. Password reset request and completion routes plus secure email delivery and replay/expiry tests.
2. A safe verification-email resend workflow and recovery for SMTP delivery failures after account creation.
3. End-to-end PostgreSQL route tests for registration, verification, rate-limit exhaustion, rotation/replay, and session revocation.
4. Workspace membership authorization on every workspace-scoped read/write, including jobs, domains, reports, exports, and audit events; current routes do not yet expose workspace data.
5. Operational review of reverse-proxy/TLS behavior, rate-limit key configuration, security headers, abuse monitoring, and deployment configuration. No production database or live SMTP provider was configured or exercised by CI.

Apply migrations explicitly from `backend/` only against a verified PostgreSQL environment. Never auto-run migrations on API startup. Do not expose protected business endpoints or mark the authentication phase complete until the remaining release gates pass.

Apply migrations explicitly from `backend/` only against a verified PostgreSQL environment. Never auto-run migrations on API startup. This repository has not been connected to a production database by this change.
