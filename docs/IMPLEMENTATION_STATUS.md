# Implementation status and release blockers

**Reviewed branch:** `main`  
**Reviewed commit:** `fb78ab4329c1fa76f89d40ed35480fa9e34a1c5a`  
**Dashboard implementation CI:** [Run 428](https://github.com/haseeb1984/Outreach-Marketing-Agent/actions/runs/39679387084) — passed for Python 3.11, 3.12 and 3.13; Python 3.12 PostgreSQL auth integration tests and dependency audit passed.  
**Scope:** Repository/source review and automated CI. The dashboard route is deployed through the Vercel Git integration, but an authenticated production browser journey has not been verified. This is not a penetration test or proof that external provider credentials work.

## Evidence-based phase matrix

| Phase / capability | Evidence currently in repository | Status |
|---|---|---|
| Public marketing and discoverability | FastAPI HTML pages for home, product, pricing, FAQ, privacy, terms and contact; robots.txt, sitemap.xml and llms.txt endpoints | Public page foundation implemented; operator must configure real support/privacy contacts and obtain jurisdiction-specific legal review before paid launch; live crawl/SEO verification remains |
| Authentication and sessions | Auth routes/store, password-reset and session/CSRF migrations, rate limiting, security tests | Backend foundation implemented; staging and full security review pending |
| Workspaces and tenant roles | Workspace membership/role checks and authorization in backend stores/routes | Foundation implemented; comprehensive cross-tenant review across every resource remains |
| Prospect CRM | Prospect routes/store, evidence-aware discovery and contact controls | Backend foundation implemented; live research-provider integration and end-to-end UI remain |
| Campaigns and approvals | Campaign/draft stores, approval queue, tests | Backend foundation implemented; complete customer-facing workflow not verified |
| Email delivery | Durable queue, SMTP adapter, send-time approval/suppression checks, idempotency | Code path exists; authenticated staging SMTP smoke test, inbox delivery and deliverability monitoring unverified |
| Reply handling | Signed generic webhook gateway, payload validation/limits, deduplication and conversation persistence | Generic foundation exists; provider-native integration and staging acceptance pending |
| Website discovery and SEO growth | Domain authorization, SSRF-aware fetch/crawl, audit/strategy/report pipeline and worker tests | Read-only backend foundation implemented; live search/analytics integrations and measured client outcomes pending |
| Subscription and billing | Migration 013 for entitlements/usage, migration 014 provider-event ledger, subscription store, billing lifecycle store, authenticated read-only `GET /api/v1/billing/entitlements` endpoint | Partial foundation only; no verified payment-provider checkout/webhook/reconciliation lifecycle established |
| Paid entitlements and quotas | Server-side entitlement decision endpoint and persistence foundation | Not release-ready: paid operations must remain fail-closed until transactional enforcement and concurrency tests cover all paid actions/jobs |
| Customer dashboard/onboarding | Responsive same-origin `/app` UI; registration/sign-in and reset request through existing auth APIs; authenticated active-workspace selector; prospect create/list; campaign create/list; draft list and approve/reject; read-only delivery activity; role-aware controls; noindex/no-store and security headers; `tests/test_customer_dashboard.py` | **Core dashboard/onboarding phase implemented; CI passed.** Remaining product gaps: workspace/project settings and invitations, connected-provider management, complete billing UX, and authenticated browser/accessibility acceptance.
| WhatsApp Business Platform | Native Meta webhook GET verification, raw-body `X-Hub-Signature-256` validation, 1 MiB request cap, deduplicated event inbox (020), workspace-scoped encrypted account registry (021), admin list/create/disable, explicit Graph API token/asset verification, and optional CRM E.164 phone field (022) | **Connection and webhook intake foundations implemented on `main`**; webhook-to-workspace processing, inbound contact matching into conversations, opt-in/template policy enforcement and outbound sending remain pending. Live sending stays disabled. |
| Provider account connections and analytics | Partial delivery/reply foundations; no complete customer-managed account-linking and verified campaign analytics workflow established | Incomplete |
| Production operations | CI, migrations, readiness checks and security tests exist | Staging secrets/provider smoke tests, accessibility/manual screen-reader checks, performance/load evidence, backup-restore drill, monitoring/incident runbook and policy review remain |

## Required next implementation order

1. Finish non-WhatsApp core backend gaps and keep the latest CI green.
2. Select/document the frontend stack, then build the customer-facing registration/onboarding and workspace dashboard against existing authenticated APIs.
3. Complete subscription lifecycle only after merchant/provider eligibility and launch jurisdiction are verified. Until then, keep billing non-operational and paid access fail-closed.
4. Add provider adapters behind interfaces and verify them with operator-controlled staging accounts; never claim a config variable proves delivery.
5. Add full tenant-isolation and quota-race coverage, then complete accessibility, performance, privacy/SEO crawl, backup/restore, monitoring and incident-readiness checks.
6. Keep WhatsApp deferred until the operator confirms Meta account setup and an eligible onboarding route that preserves the existing WhatsApp Business App number. Do not deregister or migrate the number to force setup.

## Release rules

- Work on `main` only; do not create additional branches.
- Never commit or log credentials. Use encrypted environment/secret storage.
- External sending, live payments and website writes remain gated until staging acceptance and explicit release approval.
- CI success proves only the checks that ran on that commit. It does not prove external provider operation or production readiness.
- Never fabricate delivery, conversion, SEO ranking, AI-crawler adoption or ROI metrics.


## Implementation update — 2026-10-23 (GitHub-only; no deployment or tests run)

- Added `backend/migrations/020_meta_whatsapp_webhook_inbox.sql` to persist verified Meta webhook events with payload-hash deduplication and a pending-work index.
- Added `backend/app/api/meta_whatsapp_webhook_routes.py`: Meta subscription handshake using a server-side verify token, raw-body HMAC-SHA256 signature validation, bounded request streaming, JSON/object validation, and durable persistence without logging message content.
- Registered the receiver in FastAPI and added the inbox table/migration to readiness checks.
- Documented the verify-token setting and webhook configuration in `backend/.env.example`. No real credentials were added.
- **Important limitation:** this is webhook intake only. It does not yet map phone-number IDs to workspace-owned accounts, process message/status events into CRM conversations, validate opt-in/template eligibility, or enable outbound WhatsApp sends. Those remain open implementation work.
- This update was committed directly to `main`. Automated tests, deployment, and live Meta webhook acceptance were intentionally not run, so runtime correctness is not claimed.

- Follow-up implementation: added migration `021_workspace_whatsapp_accounts.sql` and admin-authorized account management APIs. Access tokens are AES-GCM encrypted with the environment-managed provider credential key, never returned to the client, and new accounts remain `pending_verification`. The PostgreSQL migration setup now includes migrations 020 through 022. No tests were run.

- Additional implementation: added workspace-admin UI to register/list/disable Meta WhatsApp accounts. The access token input is cleared after a successful save; API responses do not return credentials. Added crawlable `/privacy`, `/terms`, and `/contact` pages, footer navigation and sitemap entries. These are preliminary product notices, not a substitute for operator-specific legal review or a real support contact.

- Follow-up implementation: added migration `022_prospect_whatsapp_phone.sql`, an optional normalized E.164 phone field in the CRM API/store/UI, and an admin action that verifies a workspace WhatsApp token against Meta's Graph API (the API version must be explicitly configured). Successful verification activates only the account record; it does **not** enable sending. Migration 022 is included in the PostgreSQL setup and readiness checks. No tests or external verification calls were run.

- Security follow-up: disabling a WhatsApp account now nulls its encrypted access-token ciphertext in the database. The connection remains fail-closed for sending even after Meta identity verification. Migration 021 stores workspace IDs as TEXT to match the existing workspace schema.

- WhatsApp event-processing implementation: migration `023_whatsapp_conversations_and_status.sql` adds tenant-scoped conversation, inbound-message and delivery-status tables. `app/services/whatsapp_event_processor.py` claims inbox events with PostgreSQL row locks, maps only active phone-number IDs to a workspace, deduplicates provider message IDs, matches known CRM contacts by normalized phone, records inbound text/statuses and marks known CRM prospects as replied. Unmapped accounts are explicitly marked rather than attached to another tenant. This is a callable worker service; a durable scheduler/queue trigger and end-to-end verification remain pending. No tests were run.

- Worker entry point added at `backend/scripts/process_whatsapp_webhooks.py`. It runs one bounded batch (up to 25 inbox events), emits only aggregate counters, rejects missing/non-PostgreSQL database configuration without exposing the DSN, and exits non-zero on processing failures. It is ready for a trusted scheduler invocation, but no scheduler has been configured or executed from this change.


## Implementation update — 2026-10-23 (GitHub-only; no tests or deployment run)

- Added `backend/app/api/whatsapp_inbox_routes.py` with authenticated, workspace-authorized, read-only endpoints for listing WhatsApp conversations and their inbound messages. Queries explicitly scope conversations, accounts, prospects and messages to the authorized workspace.
- Registered the inbox API in FastAPI and added a dashboard inbox showing recent conversations and inbound messages. No reply/send action was added.
- Hardened the webhook worker retry loop so a failed iteration cannot accidentally increment the previous event's retry counter. Status persistence uses `ON CONFLICT DO NOTHING`; migration `025_whatsapp_status_event_dedup.sql` now removes prior duplicate status rows and adds a unique expression index that also deduplicates events with missing provider timestamps.
- The inbox worker remains a one-shot command and has **not** been scheduled. Configure it through a trusted scheduler/worker after reviewing runtime/database capacity. Webhook processing and dashboard code were not tested in this update.
- WhatsApp outbound messaging remains deliberately disabled. Before enabling it, implement revocable consent/opt-out records, approved-template and 24-hour-window enforcement, durable outbound idempotency, provider failure handling, and rate/entitlement checks.


- Consent safeguard follow-up on 2026-10-23: migration `024_whatsapp_contact_preferences.sql` is now included in PostgreSQL test migration setup and backend readiness checks. The webhook processor records exact inbound opt-out keywords (`STOP`, `UNSUBSCRIBE`, `CANCEL`, `END`, `QUIT`) against the mapped workspace/account/contact; opted-out contacts are not moved to the normal replied stage. WhatsApp draft creation now requires a normalized phone number, documented opt-in evidence, and no active opt-out record. An admin-recorded, HTTPS-evidence-backed opt-in timestamps the preference as opted in so a newer explicit consent can restore eligibility. These safeguards are code changes only; no tests or deployment were run. Outbound sending remains disabled pending provider template/window enforcement, durable send idempotency, provider error reconciliation, and end-to-end acceptance verification.


- WhatsApp status deduplication follow-up on 2026-10-23: migration `025_whatsapp_status_event_dedup.sql` removes duplicate status rows and adds a unique index over provider message ID, status and a normalized timestamp expression so missing timestamps no longer bypass deduplication. Readiness and the PostgreSQL migration setup now require migration 025. The configuration-status response also accurately reports webhook signature verification and inbound persistence as implemented. No tests, provider calls or deployment were run.


- WhatsApp policy foundation follow-up on 2026-10-23: migration `026_whatsapp_template_and_window_policy.sql` adds an account-scoped provider-template registry and latest inbound timestamp fields for 24-hour customer-service-window checks. The webhook worker records latest inbound activity for mapped contacts. Added `app/services/whatsapp_send_policy.py`, a fail-closed eligibility evaluator that checks active account, contact stage, documented opt-in, account-specific opt-out, the 24-hour window, and an approved/verified provider template when outside that window. Readiness and PostgreSQL migration setup now include migration 026. **This evaluator is not yet wired into an outbound WhatsApp sender; no WhatsApp messages are sent by it, and live sending remains disabled.** No tests or deployment were run.


- Consent isolation hardening on 2026-10-23: recording a renewed WhatsApp opt-in now requires an active WhatsApp account ID, verifies that the account belongs to the workspace, and updates only that account's preference row. This avoids unintentionally clearing opt-out status across other sender accounts. This is an API/store code change; it has not been test-run.


- WhatsApp policy test coverage added on 2026-10-23: `backend/tests/test_whatsapp_send_policy.py` now covers inactive account, missing prospect, missing documented consent, do-not-contact suppression, account-specific opt-out, open customer-service window, and missing approved provider template. These tests were authored but intentionally not run in this code-first pass. This does not establish that the tests pass or enable WhatsApp sending.
