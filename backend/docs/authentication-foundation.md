# Authentication and workspace security foundation

Migration `003_authentication_foundation.sql` adds tables for users, workspace memberships, revocable sessions, email verification, password reset, and security audit events. The `auth_security.py` module provides bounded password hashing, email normalization, and opaque-token digest primitives.

## Not a released login system yet

These are schema and cryptographic primitives, not a finished authentication feature. There are deliberately no public register/login/logout routes in this change. Before routes are enabled, implement and test:

1. Email delivery and single-use verification/reset flows with short expiry and generic responses that do not reveal whether an account exists.
2. Rate limiting and abuse controls on login, registration, verification, and reset.
3. Session cookie policy (Secure, HttpOnly, SameSite), CSRF defenses where cookies authenticate state-changing requests, rotation/revocation, expiry enforcement, and session fixation protections.
4. Password reset invalidation of active sessions and account suspension checks.
5. Workspace membership authorization on every workspace-scoped read/write, including jobs, domains, reports, exports, and audit events.
6. Audit events that never include passwords, raw tokens, session cookies, or unnecessary personal data.
7. Tests for concurrent registration uniqueness, token replay/expiry, session revocation, tenant isolation, and abuse limits.

Apply migrations explicitly from `backend/` only against a verified PostgreSQL environment. Never auto-run migrations on API startup. This repository has not been connected to a production database by this change.
