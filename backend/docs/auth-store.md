# Session and workspace authorization adapter

`AuthStore` provides database-backed primitives for registration, one-time email verification, creating sessions only for active verified users, authenticating non-revoked/unexpired sessions, revoking sessions, and checking active workspace membership with an explicit role hierarchy. Registration creates the user, a personal workspace, owner membership, and a hashed verification-token record in one transaction. The raw verification token is returned once to trusted server code; this method does not send email.

## Important constraints
- The raw session token is returned once and only its SHA-256 digest is persisted.
- The caller must derive user identity from `authenticate_session`, not from a request body or query parameter.
- Every future workspace route must check membership for the requested workspace before accessing jobs, domains, reports, prospect data, or exports.
- This adapter is not wired to FastAPI routes. Email delivery, login throttling, CSRF/session cookie policy, password reset, registration abuse controls, and security audit event integration remain unimplemented.
- Do not claim that authentication is production-ready until these missing controls and real PostgreSQL integration tests are complete.
