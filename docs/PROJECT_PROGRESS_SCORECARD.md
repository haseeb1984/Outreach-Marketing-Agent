# Project Progress Scorecard

Last assessed: 2026-10-23  
Source: current `main` branch code and documentation inventory. No deployment or tests were run for this scorecard.

## How to read these numbers

These are **implementation estimates based on repository evidence**, not test-pass percentages, production readiness certifications, or claims that external providers have been live-verified. Each phase score reflects the proportion of its listed deliverables implemented in code; partial foundations count as partial credit. Production acceptance remains separately gated.

## Overall project score

| Measure | Score | Meaning |
|---|---:|---|
| Overall implementation progress | **59/100** | Weighted score across the six product phases below |
| Phase 1 — Core platform | 80% | Identity, workspace, CRM and project foundations |
| Phase 2 — Discovery and research | 50% | Public-web research and site-audit foundations; deeper competitor/influencer intelligence remains incomplete |
| Phase 3 — Provider integrations | 60% | SMTP, WhatsApp intake, policy-gated queue foundations exist; provider dispatch remains disabled |
| Phase 4 — Outreach and replies | 70% | Campaigns, approval queue, email delivery and reply ingestion foundations |
| Phase 5 — Automation and analytics | 51% | Entitlements, activity analytics, and a quota-gated WhatsApp queue exist; dispatch/scheduling and outcome attribution remain incomplete |
| Phase 6 — Production verification | 20% | Some safety/readiness code exists; CI, live provider acceptance and release validation are not complete |

Weighted overall score uses these phase weights: Phase 1 20%, Phase 2 15%, Phase 3 20%, Phase 4 20%, Phase 5 15%, Phase 6 10%. Calculation: `(80×0.20)+(50×0.15)+(60×0.20)+(70×0.20)+(51×0.15)+(20×0.10)=59.15`, rounded to **59%**.

## Phase-by-phase checkpoints

### Phase 1 — Core platform: 80%

- [x] Authentication/session foundation and password-reset flows exist in code.
- [x] Workspace roles, memberships and invitations exist in code.
- [x] Multi-project and domain-verification foundations exist in code.
- [x] CRM prospect records and workspace-scoped dashboard foundations exist.
- [ ] Account export/deletion and full onboarding/recovery acceptance are not yet demonstrated end to end.

### Phase 2 — Discovery and research: 50%

- [x] Public-web prospect search endpoint with workspace authorization and usage reservation.
- [x] Research results carry public evidence URLs and require human review before CRM use.
- [x] Read-only website crawl/audit foundation with persisted report history.
- [ ] Deeper competitor intelligence and repeatable comparison workflow remain incomplete.
- [ ] Dedicated influencer discovery/scoring and verified deduplication workflow remain incomplete.

### Phase 3 — Email and WhatsApp integrations: 60%

- [x] Workspace email-account records and encrypted credential storage foundations.
- [~] Email queue/send and SMTP diagnostics exist in code; live deliverability has not been verified here.
- [x] Meta WhatsApp webhook intake, signature validation, durable event storage and account mapping foundations exist.
- [~] WhatsApp account administration, inbound inbox and contact consent safeguards exist in code; runtime acceptance is pending.
- [~] A fail-closed policy evaluator and provider-template registry foundation now check active account, documented opt-in, account-specific opt-out, the 24-hour customer-service window, and approved/verified templates. Re-consent requires selecting an active WhatsApp account so it cannot clear opt-outs for other accounts. The evaluator is not yet wired into an outbound sender.
- [~] Durable tenant-scoped WhatsApp queue API now checks approved draft, active campaign/account, documented opt-in, account-specific opt-out, service window or verified template, and `whatsapp_sends` entitlement before queueing. Queue migration 031 is required by readiness. Provider dispatch, send idempotency at Meta, delivery reconciliation and end-to-end acceptance remain incomplete; live sending stays disabled.
- [x] Added deterministic policy unit-test cases for seven fail-closed/allowed-window decisions; they have not been executed, so passing status is unknown.

### Phase 4 — Outreach and reply management: 70%

- [x] Campaign creation and evidence-led outreach draft generation.
- [x] Human approval/rejection workflow.
- [x] Signed inbound-reply webhook and persisted conversation history foundations.
- [~] CRM reply-stage and contact-control safeguards are implemented in part; full lifecycle acceptance remains pending.
- [~] Email and WhatsApp conversation surfaces exist, but unified follow-up orchestration is not complete.

### Phase 5 — Controlled automation and analytics: 51%

- [~] Server-configured Paddle plan/checkout and signed subscription lifecycle foundations; live billing has not been verified.
- [x] Server-side usage reservation and idempotency foundations exist for key operations.
- [x] Workspace activity analytics use persisted records and avoid inventing ROI or sales figures.
- [x] Dashboard analytics now include WhatsApp inbound-message and status-event counts.
- [~] Added bounded, workspace-scoped stale-send reconciliation plus an authenticated workspace-admin recovery endpoint. Ambiguous sends remain `uncertain` and are not automatically retried; recurring scheduling and provider-record review/resolution are still incomplete.
- [~] A bounded one-shot delivery reconciliation worker is implemented; a trusted recurring schedule, safe retries across other provider operations, and verified conversion/revenue attribution remain incomplete.
- [x] Added a platform-admin dashboard API protected by an explicit server-side email allowlist; it summarizes clients/subscriptions, package catalog, per-feature quota usage, recent reservation history, and admin action history.
- [x] Added database-backed package create/edit/deactivate controls and connected the catalog to Paddle checkout/public plans/webhook mapping. Deactivation preserves historical plan mapping for existing subscription events.
- [~] Admin plan catalog and audit migrations are in code but have not been applied to a live database; frontend/API acceptance has not been run. Configure `PLATFORM_ADMIN_EMAILS` with exact verified operator email(s) before using the admin surface.

### Phase 6 — Production verification: 20%

- [x] Secret-safe logging and environment-based provider configuration foundations.
- [~] Database readiness and migration checks are present; the latest migrations have not been applied/verified against a live database in this work.
- [ ] All CI jobs passing on current `main` is not established; the previously observed CI run had a failing SMTP test.
- [ ] Live SMTP, Meta WhatsApp and Paddle sandbox/production acceptance is not established.
- [ ] Final Hostinger frontend ZIP, accessibility/performance/SEO release checks and production smoke-test evidence remain pending.

## Changes in this update

- Added migration `030_subscription_plan_slug.sql` and persisted the exact package slug on each verified Paddle subscription snapshot. Platform admin client rows now resolve the package by stable slug first, using entitlement matching only for legacy rows. This avoids displaying the wrong package when two plans share identical entitlement JSON. Readiness now expects 25 tracked migrations. The migration is not applied to a live database and no tests/deployment were run.

- Analytics API now counts inbound messages from mapped WhatsApp conversations and persisted WhatsApp delivery-status events over the selected period.
- Dashboard analytics adds separate **WhatsApp inbound** and **WhatsApp status events** metrics.
- Consent and opt-out safeguards, migrations 024/025/026 and readiness/test migration setup were committed in the preceding implementation rounds.
- Added `backend/tests/test_whatsapp_send_policy.py` with seven deterministic policy decision cases; tests were authored but not run in this code-first pass.
- Added `DeliveryStore.reconcile_stale_processing`, tenant scoping, and the CSRF-protected `POST /api/v1/deliveries/reconcile-stale` workspace-admin endpoint. It marks abandoned in-flight sends `uncertain` without automatic retries. Unit cases were updated but not run; recurring scheduling and provider-record review remain incomplete.

## Next implementation order

1. Finish WhatsApp send-time policy model: approved templates, messaging window, per-account consent eligibility, idempotent provider sends, and failure reconciliation. Keep live sending disabled until all gates are implemented and reviewed.
2. Complete durable worker scheduling and retry/lease semantics without logging secrets or personal message payloads.
3. Complete billing entitlement lifecycle and admin/client visibility, including clear usage and failure states.
4. Finish discovery/competitor research and outreach lifecycle gaps.
5. Reconcile the known CI failure, run the appropriate tests when authorized, and perform provider sandbox plus deployment acceptance.
6. Produce and inspect the Hostinger-ready frontend ZIP; deployment remains a manual user action.

## Release rule

A feature marked implemented means repository code exists. It must not be described as production-ready until tests pass and the relevant provider/database/deployment acceptance evidence is recorded.

- Added a one-shot, bounded `backend/scripts/reconcile_stale_deliveries.py` worker that processes up to 100 workspaces per run, with a per-workspace batch of 100. It never sends or retries messages and emits aggregate counters only. Scheduler configuration and provider-side resolution remain outstanding; new worker tests were authored but not run.


## Update — platform admin and billing catalog (2026-10-23)

- Added migrations `027_platform_billing_admin.sql` and `028_platform_admin_audit.sql`.
- Added `backend/app/api/platform_admin_routes.py`: allowlist-protected global overview, package create/update/soft-deactivate, per-feature usage summaries, recent usage records, and admin action audit history. Writes require authenticated session + CSRF and package edits validate Paddle price IDs and entitlement structures.
- Added `frontend/app/platform-admin/page.tsx` for admin totals, package management, client subscriptions/usage, and audit history. Frontend is source-only; no Vercel frontend deployment was triggered.
- Paddle plans now prefer the database catalog once seeded, with environment-configured plans retained only as the bootstrap fallback. Inactive plans are excluded from new checkout but retained for webhook mapping so existing subscriptions can still update.
- No tests, migrations against a live database, deployment, or workflow runs were performed in this code-first pass.

- Follow-up migration `029_unique_platform_plan_price_ids.sql` enforces one-to-one Paddle price-to-package mapping and is included in readiness and the PostgreSQL migration fixture.


## Follow-up billing safeguards — 2026-10-23

- Added a platform-admin-only import action for environment-configured Paddle plans; existing database packages are not overwritten.
- Package catalog writes and audit events now share a database transaction.
- Price IDs cannot be changed when subscription snapshots are linked to the package entitlement set; use a new package for future price changes.
- Added plan-input validation tests. They have not been run, and no score increase is claimed from unverified code.

- Hardened Paddle subscription mapping: signed webhooks require custom_data.plan_id to match the single package identified by provider price ID, and reject missing event/subscription identities instead of stringifying absent values. Added backend/tests/test_paddle_plan_mapping.py for matching, mismatch, missing metadata, unknown price and ambiguous mapping cases. Tests were authored but not run.

- Bootstrap billing configuration now validates package slug syntax, Paddle price-ID syntax and duplicate price IDs before exposing plans or accepting checkout/webhook mapping. Expanded the Paddle mapping test file for malformed bootstrap catalog cases; tests remain unrun.

- WhatsApp operations visibility: added a workspace-authorized, paginated webhook-event listing with pending/processed/error counts, restricted to Meta phone-number IDs mapped to that workspace. The endpoint deliberately withholds raw event payloads and message content and does not trigger processing or retries. Code committed on `main`; tests and deployment were not run.


### Platform admin client search — 2026-10-23

- Added client-side filtering by workspace name/ID, owner email, package, and subscription status, with visible filtered/loaded counts.
- This improves lookup for the loaded set only (API currently returns up to 500 clients); it is not full historical reporting.
- No tests, deployment, or workflow were run.


### WhatsApp event-processing hardening — 2026-10-23

- Added normalized standalone opt-out and explicit opt-in command recognition for inbound WhatsApp text messages.
- Delivery-status saved counts now increment only when the database actually inserts a new event, not for duplicates.
- Added regression tests for command matching, ordinary-prose false positives, message-body truncation, and timestamp parsing. Tests have not been run; this does not enable outbound sending.


- WhatsApp reliability follow-up (2026-10-23): service-window timestamps now use the provider timestamp bounded by server receipt time; exhausted webhook events (8+ attempts) are exposed as a separate workspace-scoped `dead_letter` state and count. This improves safety and operator visibility but adds a workspace-admin-only manual requeue for a single exhausted event, but does not enable outbound messaging. No tests were run; overall estimate remains **59/100**.


- WhatsApp consent/recovery follow-up (2026-10-23): consent updates now use bounded inbound event timestamps and guard against out-of-order STOP/START events overwriting newer consent state. A workspace admin can requeue one exhausted webhook event after review using a CSRF-protected endpoint scoped to an active mapped account. Requeue does not send messages; the trusted worker must run separately. Added timestamp regression tests but did not execute them. Overall implementation estimate remains **59/100**.


- Platform-admin pagination (2026-10-23): client inventory is now paginated server-side with total workspace count and previous/next controls in the admin UI; search explicitly applies to the current page. This removes the fixed 500-workspace view cap, but the dashboard remains unverified in an authenticated browser. No tests or deployment were run.


- Platform-admin reporting extension (2026-10-23): client inventory and usage-reservation history now support server-side page size/offset, total counts, and dashboard navigation. The prior 500-client and 200-record display caps are removed for these lists. Per-feature aggregation and audit history remain bounded top-N views; no tests or authenticated browser acceptance were run. Overall score remains **59/100**.


- Platform-admin audit history now supports bounded server-side pagination, total count and dashboard navigation alongside client and usage-history paging. Per-feature aggregate reporting remains capped at 2,000 workspace-feature rows. This is source implementation only; tests and authenticated browser acceptance remain pending, so overall score stays **59/100**.


- WhatsApp send-policy hardening (2026-10-23): eligibility now fails closed when an active account has no encrypted credential and requires a workspace-matched, approved WhatsApp draft attached to an active campaign before allowing either an open customer-service-window send or a verified-template send. Added/updated deterministic test fixtures for these gates. The evaluator is still not connected to an outbound sender; live WhatsApp sending remains disabled. Tests were not run and the overall score remains **59/100**.


- WhatsApp outbound queue (2026-10-23): added migration 031, tenant-scoped idempotent queue storage, admin-only CSRF-protected queue API, queue history endpoint, and authored store tests. Queue creation reserves the `whatsapp_sends` entitlement and calls the fail-closed send-policy evaluator. The API explicitly does not dispatch messages; no live sending, tests, deployment, or live migration was performed. Readiness migration count is now 26.
