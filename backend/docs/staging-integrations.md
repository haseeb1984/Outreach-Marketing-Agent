# Staging integration setup: SMTP and WhatsApp Business

This guide is for **staging only**. Do not paste credentials into chat, issue trackers, screenshots, or logs. Set them in the staging host's encrypted environment/secret settings. For local development, use the ignored `backend/.env` copied from `backend/.env.example`.

## 1. SMTP staging

Set these environment variables in the staging API service:

- `SMTP_HOST`: the SMTP hostname supplied by the email provider.
- `SMTP_PORT`: provider-approved submission port (commonly 587).
- `SMTP_USERNAME` and `SMTP_PASSWORD`: staging SMTP credentials, stored as encrypted secrets.
- `SMTP_FROM_EMAIL`: sender address verified with the provider.
- `SMTP_FROM_NAME`: customer-facing sender label.
- `SMTP_STARTTLS=true`: required; the adapter rejects configurations that do not enable STARTTLS.
- `PUBLIC_BASE_URL`: the actual HTTPS staging origin; never use the example placeholder.
- `ENVIRONMENT=staging`: set the environment label explicitly.
- `DATABASE_URL` and `SECRET_KEY`: staging-only values, independent from production.

Use a dedicated staging sender/domain or provider sandbox and send only to an address you control. Never use production customer lists for smoke tests.

After saving encrypted variables, restart/redeploy the staging API so settings are reloaded. Apply the repository migrations using the documented migration process; the API deliberately does not run migrations automatically. Check `GET /ready` and the authenticated, workspace-scoped `GET /api/v1/integrations/status?workspace_id=...` endpoint. The latter reports only missing variable *names*, whether STARTTLS is enabled, and whether a connection test has been run; it never returns credentials. A complete configuration is not proof that the username/password work.

### SMTP smoke-test acceptance

1. Confirm `/ready` returns ready and the staging schema includes migrations 001–012.
2. Confirm the integration-status endpoint is accessible only to an authenticated workspace member and reports no secret values.
3. Create a staging-only prospect using an inbox you control, record any required lawful contact basis/consent, create a draft, and approve it explicitly.
4. Enqueue and send that approved draft from the staging workspace only.
5. Confirm the provider's SMTP submission logs and recipient inbox. A recorded `sent` means the SMTP handoff completed; it does not prove inbox placement.
6. For a timeout/disconnect, verify the delivery is `uncertain` and cannot be resent automatically. Reconcile with provider logs before any manual action.
7. Verify suppressed contacts and unapproved drafts cannot be sent. Do not enable bulk or scheduled sending during this smoke test.

Do not claim the staging email path is verified until the above has been performed with the actual staging secret settings and provider.

## 2. WhatsApp Business Platform onboarding

WhatsApp sending remains disabled. The application must use Meta's official WhatsApp Business Platform/Cloud API or an explicitly approved official provider; do not use WhatsApp Web automation, session cookies, unofficial libraries, or browser scraping.

An administrator must complete these steps in the provider's own console:

1. Create/choose the Meta Business Portfolio and WhatsApp Business Account (WABA), and complete required business verification.
2. Create a Meta developer app, add the WhatsApp product, and associate the correct WABA and phone number.
3. For staging, use a provider-supported test number/recipient allowlist where available. Confirm recipient opt-in and template requirements before sending any template message.
4. Generate a least-privilege, long-lived/system-user access token appropriate for the deployed app. Keep it only in encrypted staging environment settings; never place it in frontend code, Git, support tickets, or logs.
5. Configure the provider's webhook callback to the staging HTTPS endpoint and set the webhook verification token and app secret as encrypted secrets. Subscribe only to the required message/status events.
6. Verify webhook authenticity using the provider's documented signature algorithm over the **raw request body** before parsing or persisting events. The current generic inbound-reply HMAC gateway is not, by itself, a Meta webhook adapter; provider-specific verification and payload normalization must be implemented and tested before connecting Meta.
7. Store provider account/phone identifiers scoped to the owning workspace. Do not share one tenant's phone number, token, messages, or webhook mapping with another tenant.
8. Confirm opt-in evidence, suppression/opt-out handling, template approval, rate limits, audit trail, inbound reply mapping, duplicate-event handling, and status webhooks in staging.
9. Test only with approved test recipients. Keep production WhatsApp sending disabled until security review and explicit release approval.

### WhatsApp secrets/identifiers to provision later

Once the official adapter is implemented, use encrypted environment settings or a secret manager for the provider token, app secret, webhook verification token, and any signing secret. Store non-secret identifiers (such as WABA ID and phone-number ID) in the provider/workspace configuration model with strict tenant authorization where possible. Do not add real values to `.env.example`; placeholders only.

## Current implementation boundary

- SMTP: configuration is environment-backed; an authenticated integration-status endpoint checks presence and TLS requirements without exposing values. It does not perform a network/authentication test.
- WhatsApp: official-provider adapter and provider-specific webhook signature verification are not implemented, so live sending remains disabled.
- Never treat a status check, mocked test, or CI pass as proof of successful external delivery.
