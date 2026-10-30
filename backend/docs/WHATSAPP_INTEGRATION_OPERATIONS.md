# WhatsApp Business Cloud integration operations

## Implemented application flow

1. A workspace admin creates a WhatsApp account with WABA ID, phone-number ID and access token. The token is encrypted at rest and never returned.
2. **Verify** calls the configured Meta Graph API version to validate the phone-number ID and that it belongs to the selected WABA. It then calls `POST /{Waba-ID}/subscribed_apps` and only activates the account after Meta confirms the app subscription.
3. The public webhook endpoint is `GET/POST /api/v1/webhooks/meta/whatsapp`. Configure that exact HTTPS callback URL in the Meta app, set the verify token, and subscribe the app to the `messages` field. The POST handler validates the raw-body `X-Hub-Signature-256`, bounds payload size, splits events by phone-number ID and persists idempotently.
4. A trusted scheduled job processes inbound messages and delivery-status events. It creates tenant-scoped conversations, applies STOP/UNSUBSCRIBE opt-outs, accepts explicit START/UNSTOP re-consent, and reconciles provider status callbacks against outbound delivery rows.
5. Approved WhatsApp drafts can be queued from the dashboard. Queue creation reserves quota and checks account-specific documented opt-in, current opt-out, active campaign, approved draft, phone validity and the 24-hour customer-service window / approved-template rule.
6. Before each provider request, the worker rechecks the subscription reservation and all send-policy conditions, resolves the active tenant's encrypted token, and makes one Meta API attempt. Definite rejections release quota; accepted or ambiguous outcomes consume quota and are never blindly retried.

## Required server settings

- `DATABASE_URL`: PostgreSQL database with migrations through `038_whatsapp_outbound_queue_leases.sql`.
- `PROVIDER_CREDENTIAL_ENCRYPTION_KEY`: stable URL-safe base64-encoded 32-byte key.
- `META_WHATSAPP_APP_SECRET`: Meta app secret, at least 32 bytes, used for webhook signature validation.
- `META_WHATSAPP_WEBHOOK_VERIFY_TOKEN`: unique random verify token, at least 32 bytes.
- `META_GRAPH_API_VERSION`: pinned supported version in `vNN.0` format.
- `CRON_SECRET`: unique random scheduler bearer secret, at least 32 bytes.
- `WHATSAPP_DISPATCH_ENABLED=false` by default. Keep false until Meta app review/live number setup, sandbox acceptance, template behavior, quota reconciliation and incident handling are approved. Set true only in the server environment to enable the one-shot dispatch endpoint and the standalone worker.

Generate secrets with Python:
```sh
python -c "import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

## Scheduled worker

The repository workflow `.github/workflows/process-due-deliveries.yml` runs every five minutes and also supports manual dispatch. Configure GitHub Actions secrets `BACKEND_BASE_URL` (HTTPS API origin) and `CRON_SECRET` (same value as the backend). It processes email deliveries, verified WhatsApp webhook events and, only when the server flag is enabled, a bounded WhatsApp outbound batch.

The authenticated operations endpoints are:

- `POST /api/v1/integrations/whatsapp/inbox/webhook-events/process-pending-system?batch_size=50`
- `POST /api/v1/integrations/whatsapp/outbound/process-queued?limit=10`

Both require `Authorization: Bearer $CRON_SECRET`. The outbound endpoint safely returns a skipped result while the server-side dispatch flag is off.

A continuous alternative is `python -m app.workers.whatsapp_dispatch_worker` from `backend/`. The worker requires both the parsed setting and exact environment opt-in to be true. Do not run the continuous worker and scheduled dispatcher concurrently unless the deployment intentionally wants multiple competing workers; row leases and `SKIP LOCKED` prevent duplicate claims.

## Meta dashboard and external activation still required

Application code cannot create or approve the Meta Business Manager, complete business verification, register/verify a production phone number, obtain WhatsApp permissions, pass Meta App Review, or approve message templates on the customer's behalf. The operator must configure the webhook callback and verify token in Meta, subscribe to the `messages` webhook field, grant the required WhatsApp permissions, and complete Meta's live onboarding.

The sender currently supports plain text inside the 24-hour customer-service window and **parameter-free approved templates** outside it. Templates requiring body/header/button variables must not be queued for dispatch until parameter mapping is implemented. Do not enable live dispatch for variable-bearing templates.

## Operational safety

- Never use purchased or scraped phone lists; record lawful, account-specific opt-in evidence.
- STOP/UNSUBSCRIBE/CANCEL/END/QUIT suppress queued sends. START/UNSTOP/SUBSCRIBE records renewed explicit opt-in; workspace contact controls and account-specific evidence still apply.
- `uncertain` outcomes require provider evidence/manual reconciliation and are not automatically retried.
- Queue leases that expire become uncertain; no expired in-flight request is sent again automatically.
- Disabling an account removes its encrypted token and cancels queued deliveries, releasing their reservations.
- Meta webhook delivery is asynchronous; a successful API response does not prove a message was delivered or read.
