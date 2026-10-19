# Session and workspace authorization adapter

`AuthStore` provides database-backed primitives for registration, one-time email verification, creating sessions only for active verified users, authenticating non-revoked/unexpired sessions, revoking sessions, and checking active workspace membership with an explicit role hierarchy. Registration creates the user, a personal workspace, owner membership, and a hashed verification-token record in one transaction. The raw verification token is returned once to trusted server code; this method does not send email.

## Important constraints
- The raw session token is returned once and only its SHA-256 digest is persisted.
- The caller must derive user identity from `authenticate_session`, not from a request body or query parameter.
- Every future workspace route must check membership for the requested workspace before accessing jobs, domains, reports, prospect data, or exports.
- This adapter is not wired to FastAPI routes. Email delivery, login throttling, CSRF/session cookie policy, password reset, registration abuse controls, and security audit event integration remain unimplemented.
- Do not claim that authentication is production-ready until these missing controls and real PostgreSQL integration tests are complete.

## Email delivery adapter

SMTPEmailDelivery is an optional server-side adapter for verification emails. Configure SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL, and PUBLIC_BASE_URL using deployment environment variables/secrets. It requires an HTTPS origin and STARTTLS, and fails closed when configuration is incomplete. The adapter does not log the verification token or email body.

This adapter is not called automatically by registration yet. Before public routes, wire it through bounded delivery, add rate limits and generic responses, and test against a real SMTP sandbox/provider. Never return verification tokens from public API responses.