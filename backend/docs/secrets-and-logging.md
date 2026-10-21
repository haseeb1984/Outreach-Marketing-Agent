# Secrets and sensitive-log policy

## Configuration
- Local development: copy `backend/.env.example` to `backend/.env`; keep real values only in the ignored `.env` file.
- Deployment: inject secrets through the hosting provider's encrypted environment-variable/secret store. Never commit real credentials, include them in ZIP artifacts, or put them in frontend JavaScript.
- Use distinct credentials per environment, least-privilege database users, and rotate any credential suspected to be exposed.
- `SECRET_KEY`, `DATABASE_URL`, SMTP credentials, API keys, OAuth secrets, webhook secrets, and provider tokens must be read from environment-backed settings. New integrations must add documented blank placeholders to the example file, never real values.
- `.env.example` is a template only. Its domain is deliberately a placeholder and must be replaced before sending real verification emails.

## Logging and error handling
- Never log request bodies, Authorization headers, cookies, passwords, raw verification/reset/session tokens, connection strings, SMTP usernames/passwords, provider API keys, or full verification URLs.
- Log stable error codes and a correlation/request ID, not exception text from credential-bearing integrations. Do not return raw exception messages or tracebacks to clients.
- Do not enable HTTP wire/debug logging for SMTP, HTTP clients, database drivers, or auth middleware in production without an explicit reviewed redaction policy.
- CI output and test failures must not print environment values. Use dummy test credentials only.
- Store only SHA-256 digests of opaque verification/reset/session tokens in the database; expose a raw token only once to the trusted delivery/session boundary.
- Audit events must contain event type/outcome and minimal non-secret metadata, never tokens, passwords, cookies, or credential-bearing URLs.

## Release gate
Before enabling account routes, add automated checks that captured application logs and client error responses contain none of the supplied canary secrets; verify rate limits, CSRF/cookie settings, token replay/expiry, tenant isolation, and production environment configuration. Do not run migrations automatically at API startup.


## Outbound delivery outcome handling
- A successful SMTP handoff is recorded as `sent`; missing SMTP configuration or pre-send input validation is recorded as `failed`.
- A timeout, disconnect, or unexpected SMTP adapter exception is recorded as `uncertain`. The remote server may already have accepted the message, so the system must not automatically retry it.
- Operators should reconcile an `uncertain` record against the provider's delivery logs/mailbox before deciding what to do. The current product does not provide an automated reconciliation API and does not claim mailbox delivery from an SMTP handoff.
- The uncertainty state is terminal for the send endpoint: it is not claimable again. Never reset it to `queued` without external evidence that the first send was not accepted.
