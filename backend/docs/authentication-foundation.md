# Authentication HTTP phase

The FastAPI app exposes /api/v1/auth/register, /verify-email, /login, /me, /rotate, /logout, /password-reset/request, and /password-reset/confirm. Verification and password-reset landing pages require an explicit POST to consume tokens; GET requests alone do not activate or consume a token.

The routes use PostgreSQL-backed AuthStore and AuthRateLimiter instances initialized only when DATABASE_URL is configured. Rate limiting additionally requires a SECRET_KEY of at least 32 bytes. Registration and password-reset email delivery require a correctly configured SMTP adapter and HTTPS PUBLIC_BASE_URL. Startup never applies migrations automatically.

## Required deployment configuration

1. Configure a real HTTPS PUBLIC_BASE_URL, PostgreSQL DATABASE_URL, high-entropy SECRET_KEY, and SMTP settings in the host's encrypted environment settings.
2. Apply migrations explicitly with python -m app.db.migrations; migrations 001–006 are required for the current readiness check.
3. Verify SMTP delivery, HTTPS cookie behavior, database-backed rate limits, and reset/verification links in a non-production environment before enabling public registration.
4. Configure proxy trust only after verifying deployment forwarding and egress policies. Client IP rate limits intentionally ignore forwarded headers by default.
5. Do not claim production readiness until the PostgreSQL integration suite, deployment smoke tests, recovery procedures, and real email delivery have been verified.

The API does not make billing, outreach sending, or a complete customer dashboard available. Authentication is one backend phase, not proof that the full SaaS is complete.
