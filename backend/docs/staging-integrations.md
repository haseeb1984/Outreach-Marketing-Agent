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

After saving encrypted variables, restart/redeploy the staging API so settings are reloaded. Apply the repository migrations using the documented migration process; the API deliberately does not run migrations automatically. Check `GET /ready` and the authenticated, workspace-scoped `GET /api/v1/integrations/status?workspace_id=...` endpoint. The latter reports only missing variable *names*, whether STARTTLS is enabled, and a `connection_tested=false` marker because the status read does not run a connection test and test results are not persisted; it never returns credentials. A complete configuration is not proof that the username/password work.

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

1. Update the WhatsApp Business App on the phone and confirm the existing number remains active. Do **not** delete/deregister it to force API onboarding.
2. Open [Meta's official Cloud API guide](https://developers.facebook.com/docs/whatsapp/cloud-api/overview), create/choose a Meta developer app, add WhatsApp, and associate the intended Business Portfolio/WABA.
3. Because this number must remain in the Business App, use an onboarding flow that explicitly offers **WhatsApp Business App Coexistence** for that same number. If the Meta flow only offers migration/deregistration or does not show the app-link approval, stop; do not proceed with a destructive migration. Eligibility is determined by Meta and the supported onboarding path.
4. For the SaaS's future customer onboarding, plan for [Meta Embedded Signup](https://www.postman.com/meta/whatsapp-business-platform/collection/du6gzjv/embedded-signup) and Tech Provider/Solution Partner requirements; do not hard-code the owner's WABA or phone ID as a global multi-tenant integration.
5. For staging, use a provider-supported test number/recipient allowlist where available. Confirm recipient opt-in and template requirements before sending any template message.
6. Generate a least-privilege, long-lived/system-user access token appropriate for the deployed app. Keep it only in encrypted staging environment settings; never place it in frontend code, Git, support tickets, or logs.
7. Set the staging variables listed below. The integration status endpoint reports presence only; it does not prove token validity, number eligibility, or delivery.
8. Configure a staging HTTPS callback only after a provider-specific GET verification handshake, raw-body `X-Hub-Signature-256` validation, event normalization, tenant/phone mapping, persistence, idempotency, and status handling have been implemented and tested. The current code deliberately does **not** claim that Meta webhook ingestion is ready.
9. Confirm opt-in evidence, suppression/opt-out handling, template approval, rate limits, audit trail, inbound reply mapping, duplicate-event handling, and status webhooks in staging.
10. Test only with approved test recipients. Keep production WhatsApp sending disabled until security review and explicit release approval.

### WhatsApp secrets/identifiers to provision later

Set these staging variables only in encrypted environment settings or a secret manager: `META_WHATSAPP_ACCESS_TOKEN`, `META_WHATSAPP_APP_SECRET`, and `META_WHATSAPP_WEBHOOK_VERIFY_TOKEN`. For single-tenant staging, `META_WHATSAPP_PHONE_NUMBER_ID` and `META_WHATSAPP_WABA_ID` are non-secret identifiers. For multi-tenant production, these identifiers and credential references must be workspace-scoped in the database/secret manager, not global settings. Do not add real values to `.env.example`; placeholders only.

## Current implementation boundary

- SMTP: configuration is environment-backed; an authenticated integration-status endpoint checks presence and TLS requirements without exposing values. It does not perform a network/authentication test.
- WhatsApp: environment-backed Meta setup readiness is now reported without leaking values. Coexistence eligibility, Meta webhook handshake/signature verification, event persistence, tenant asset mapping, outbound Cloud API sending, and provider status handling remain unimplemented; live sending remains disabled.
- Never treat a status check, mocked test, or CI pass as proof of successful external delivery.


### Safe SMTP connection/authentication check

The API exposes an explicit admin-only `POST /api/v1/integrations/smtp/test?workspace_id=...` endpoint in staging and production. It requires an authenticated session, CSRF validation, and workspace-admin authorization; it remains unavailable in development/other environment labels. Set `ENVIRONMENT=production` on the production deployment (or `ENVIRONMENT=staging` for staging). The endpoint validates SMTP STARTTLS configuration, then performs EHLO, STARTTLS, EHLO, and authentication. It does **not** send a message. Provider exception details and credentials are never returned. A successful response proves only that the configured SMTP server accepted a TLS-authenticated session at test time. The result is returned for that request and is not persisted in integration status; it does not prove message handoff or inbox receipt.
