# Authentication and workspace security foundation

Migrations `003_authentication_foundation.sql` and `004_auth_rate_limits.sql` add tables for users, workspace memberships, revocable sessions, email verification, password reset, security audit events, and keyed rate-limit buckets. The `auth_security.py` module provides bounded password hashing, email normalization, and opaque-token digest primitives. The `auth_rate_limiter.py` module atomically increments PostgreSQL fixed-window buckets while storing only an HMAC digest of a namespaced identifier. Password authentication now performs a scrypt verification against a precomputed dummy hash when no active, verified account is found, reducing account-state timing differences. This does not replace route-level rate limiting.

## Not a released login system yet

These are schema and cryptographic primitives, not a finished authentication feature. There are deliberately no public register/login/logout routes in this change. Before routes are enabled, implement and test:

1. Email delivery and single-use verification/reset flows with short expiry and generic responses that do not reveal whether an account exists.
2. Wire the database-backed rate limiter into login, registration, verification, and reset routes, with independent IP/account buckets, generic responses, and appropriate `429` handling. The limiter exists as a primitive but is not yet connected to public routes.
3. Session cookie policy (Secure, HttpOnly, SameSite), CSRF defenses where cookies authenticate state-changing requests, rotation/revocation, expiry enforcement, and session fixation protections. `AuthStore.rotate_session()` now provides an atomic single-use replacement primitive; it is not yet wired to an HTTP login/privilege-change route.
4. Password reset invalidation of active sessions and account suspension checks. `AuthStore.issue_password_reset()` issues a bounded, one-time token for verified active accounts; `reset_password()` consumes a live token, updates the password, consumes outstanding reset tokens, revokes active sessions, and writes a secret-free audit event. These methods are not yet wired to HTTP routes or email delivery.
5. Workspace membership authorization on every workspace-scoped read/write, including jobs, domains, reports, exports, and audit events.
6. Audit events that never include passwords, raw tokens, session cookies, or unnecessary personal data.
7. Tests for concurrent registration uniqueness, token replay/expiry, session revocation, tenant isolation, and end-to-end abuse limits, including concurrent requests and database-backed behavior.

The current automated CI suite has passed on Python 3.11, 3.12, and 3.13, including the PostgreSQL authentication integration tests and dependency audit on Python 3.12. This verifies the existing primitives and regression coverage only; it does not certify a public authentication flow, because the HTTP routes remain intentionally unimplemented.

Apply migrations explicitly from `backend/` only against a verified PostgreSQL environment. Never auto-run migrations on API startup. This repository has not been connected to a production database by this change.
