# Session and workspace authorization adapter

`AuthStore` adds database-backed primitives for creating sessions only for active, email-verified users; authenticating a non-revoked, unexpired session; revoking sessions; and checking active workspace membership with an explicit role hierarchy.

## Important constraints
- The raw session token is returned once and only its SHA-256 digest is persisted.
- The caller must derive user identity from `authenticate_session`, not from a request body or query parameter.
- Every future workspace route must check membership for the requested workspace before accessing jobs, domains, reports, prospect data, or exports.
- This adapter is not yet wired to FastAPI routes and does not provide CSRF protection, login throttling, email delivery, registration, or password-reset workflows.
- Do not claim that authentication is production-ready until these missing controls and real PostgreSQL integration tests are complete.
