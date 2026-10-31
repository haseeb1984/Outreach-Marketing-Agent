# WhatsApp Business Cloud integration operations

## Implemented application flow

1. A workspace admin creates a WhatsApp account with WABA ID, phone-number ID and access token. The token is encrypted at rest and never returned.
2. **Verify** calls the configured Meta Graph API version to validate the phone-number ID and that it belongs to the selected WABA. It then calls `POST /{Waba-ID}/subscribed_apps` and only activates the account after Meta confirms the app subscription.
3. The public webhook endpoint is `GET/POST /api/v1/webhooks/meta/whatsapp`. Configure that exact HTTPS callback URL in the Meta app, set the verify token, and subscribe the app to the `messages` field. The POST handler validates the raw-body `X-Hub-Signature-256`, bounds payload size, splits events by phone-number ID and persists idempotently.
4. A trusted scheduled job processes inbound messages and delivery-status events. It creates tenant-scoped conversations, applies STOP/UNSUBSCRIBE opt-outs, accepts explicit START/UNSTOP re-consent, and reconciles provider status callbacks against outbound delivery rows.
5. Approved WhatsApp drafts can be queued from the dashboard. Queue creation reserves quota and checks account-specific documented opt-in, current opt-out, active campaign, approved draft, phone validity and the 24-hour customer-service window / approved-template rule.
6. Before each provider request, the worker rechecks the subscription reservation and all send-policy conditions, resolves the active tenant's encrypted token, and makes one Meta API attempt. Definite rejections release quota; accepted or ambiguous outcomes consume quota and are never blindly retried.

## WhatsApp inbox team operations

Workspace owners/admins can select up to 100 visible conversations and atomically bulk-update assignment, inbox status and priority with `POST /api/v1/integrations/whatsapp/inbox/conversations/bulk-update?workspace_id=...`. The request contains `conversation_ids` and any subset of `assigned_to_user_id` (use null to unassign), `inbox_status` and `priority`. Every conversation must belong to the workspace; invalid/missing IDs reject the whole operation. Assignee membership is checked before changes, and each changed field writes an activity event in the same database transaction. The endpoint requires admin role and CSRF protection.

## Required server settings

- `DATABASE_URL`: PostgreSQL database with migrations through `044_whatsapp_inbox_collaboration.sql`.
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

The sender supports plain text inside the 24-hour customer-service window and approved templates outside it. Text variables in BODY and TEXT HEADER components and dynamic URL button parameters are synced from Meta, persisted per delivery, validated against the approved component schema, and sent as Meta component parameters. Media headers remain rejected until their upload/handle mapping is implemented. Keep those templates out of outbound campaigns.

## Template component support

- Supported: BODY and TEXT HEADER text placeholders plus dynamic URL button placeholders, validated against the latest synchronized Meta-approved schema.
- Dynamic URL button parameters use `{"buttons":[{"index":0,"sub_type":"url","value":"tracking-path"}]}`; indexes are zero-based and must match each approved dynamic URL button.
- Static quick-reply, phone-number and copy-code buttons need no dynamic parameter. Unsupported button types and media headers fail closed before provider dispatch.
- Template parameter values are supplied as a JSON object, for example `{"body":["First name","Company"],"buttons":[{"index":0,"sub_type":"url","value":"tracking-path"}]}`. The dashboard prompts for this object only when a selected approved template contains placeholders.
- Re-sync templates after any Meta edit or approval-state change; stale approvals are revoked before the current catalogue is persisted.

## Operational safety

- Never use purchased or scraped phone lists; record lawful, account-specific opt-in evidence.
- STOP/UNSUBSCRIBE/CANCEL/END/QUIT suppress queued sends. START/UNSTOP/SUBSCRIBE records renewed explicit opt-in; workspace contact controls and account-specific evidence still apply.
- `uncertain` outcomes require provider evidence/manual reconciliation and are not automatically retried.
- Queue leases that expire become uncertain; no expired in-flight request is sent again automatically.
- Disabling an account removes its encrypted token and cancels queued deliveries, releasing their reservations.
- Meta webhook delivery is asynchronous; a successful API response does not prove a message was delivered or read.


## Inbound attachment storage

- Inbound image, video, audio, document and sticker metadata is captured from the signed webhook.
- Workspace admins can trigger a download with `POST /api/v1/integrations/whatsapp/inbox/messages/{message_id}/media/download?workspace_id=...&account_id=...`.
- The downloader resolves the active account token server-side, fetches only Meta's approved HTTPS media hosts, rejects redirects and unsupported MIME types, caps attachments at 16 MiB, and stores AES-GCM ciphertext in PostgreSQL. Workspace/account/message IDs are authenticated as encryption associated data.
- Workspace members with viewer access can retrieve decrypted bytes from `GET /api/v1/integrations/whatsapp/inbox/messages/{message_id}/media?workspace_id=...`. Responses are attachment-only, private/no-store and nosniff. Media is not exposed through public URLs.
- Workspace admins can permanently remove stored attachment bytes with `DELETE /api/v1/integrations/whatsapp/inbox/messages/{message_id}/media?workspace_id=...`; the inbound message and non-content metadata remain for conversation history. Downloads verify Meta's SHA-256 digest before encryption.
- Apply migration `043_whatsapp_inbound_media_storage.sql` before using attachment endpoints. Configure the same stable `PROVIDER_CREDENTIAL_ENCRYPTION_KEY` used for account credentials; losing it makes stored media unrecoverable.


## Inbox ownership and team collaboration

- Apply migration `044_whatsapp_inbox_collaboration.sql` before using assignment, lifecycle or internal-note endpoints.
- Workspace admins can assign a conversation to an active workspace member with `PATCH /api/v1/integrations/whatsapp/inbox/conversations/{conversation_id}?workspace_id=...`; send `assigned_to_user_id` (or null to unassign), `inbox_status` (`open|pending|resolved`) and/or `priority` (`low|normal|high|urgent`). Assignee membership is re-authorized against the same workspace.
- Workspace members and above can add and read internal-only notes using `POST/GET /api/v1/integrations/whatsapp/inbox/conversations/{conversation_id}/notes?workspace_id=...`. Notes are stored separately and are never included in outbound Meta payloads. Workspace admins can delete notes.
- Conversation lists include current assignee, lifecycle status and priority. Resolved conversations remain available in history and can be reopened by an admin.
- These collaboration actions do not initiate outbound messages or alter consent state.


## Conversation activity history

- Apply migration `045_whatsapp_conversation_activity.sql` after migration 044.
- The inbox exposes `GET /api/v1/integrations/whatsapp/inbox/conversations/{conversation_id}/activity?workspace_id=...` to workspace viewers and above. Results are newest-first, bounded to 100 records, and can be paginated with `before_id`.
- Assignment, lifecycle status and priority changes are recorded in the same database transaction as the conversation update. Internal note creation and deletion are also recorded transactionally.
- Activity entries contain the actor user ID, event type, timestamp and minimal change metadata. Note bodies and message contents are deliberately excluded. Entries are append-only through the application API and cascade only when the parent conversation is deleted.


## Inbox filtering and search

- The conversation list endpoint supports `assigned_to_me=true`, `unassigned=true`, `inbox_status=open|pending|resolved`, `priority=low|normal|high|urgent`, and `search=...` alongside the existing bounded `limit` and `offset` parameters.
- `assigned_to_me` is evaluated against the authenticated session user; clients cannot supply an arbitrary assignee identity for this filter.
- Search matches the WhatsApp contact identifier, linked prospect name/company, and latest inbound message text. All conditions remain scoped to the authorized workspace.
- The dashboard provides assignment, status, priority and text-search controls with apply and clear actions.
