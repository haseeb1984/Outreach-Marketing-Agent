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
| Phase 3 — Provider integrations | 58% | SMTP and WhatsApp integration foundations exist; WhatsApp outbound is disabled |
| Phase 4 — Outreach and replies | 70% | Campaigns, approval queue, email delivery and reply ingestion foundations |
| Phase 5 — Automation and analytics | 50% | Entitlements and activity analytics exist; durable scheduling and outcome attribution remain incomplete |
| Phase 6 — Production verification | 20% | Some safety/readiness code exists; CI, live provider acceptance and release validation are not complete |

Weighted overall score uses these phase weights: Phase 1 20%, Phase 2 15%, Phase 3 20%, Phase 4 20%, Phase 5 15%, Phase 6 10%. Calculation: `(80×0.20)+(50×0.15)+(58×0.20)+(70×0.20)+(50×0.15)+(20×0.10)=58.60`, rounded to **59%**.

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

### Phase 3 — Email and WhatsApp integrations: 58%

- [x] Workspace email-account records and encrypted credential storage foundations.
- [~] Email queue/send and SMTP diagnostics exist in code; live deliverability has not been verified here.
- [x] Meta WhatsApp webhook intake, signature validation, durable event storage and account mapping foundations exist.
- [~] WhatsApp account administration, inbound inbox and contact consent safeguards exist in code; runtime acceptance is pending.
- [~] A fail-closed policy evaluator and provider-template registry foundation now check active account, documented opt-in, account-specific opt-out, the 24-hour customer-service window, and approved/verified templates. Re-consent requires selecting an active WhatsApp account so it cannot clear opt-outs for other accounts. The evaluator is not yet wired into an outbound sender.
- [ ] WhatsApp outbound sending is intentionally disabled until the policy is integrated, durable provider sends/error reconciliation are implemented, and the end-to-end flow is verified.
- [x] Added deterministic policy unit-test cases for seven fail-closed/allowed-window decisions; they have not been executed, so passing status is unknown.

### Phase 4 — Outreach and reply management: 70%

- [x] Campaign creation and evidence-led outreach draft generation.
- [x] Human approval/rejection workflow.
- [x] Signed inbound-reply webhook and persisted conversation history foundations.
- [~] CRM reply-stage and contact-control safeguards are implemented in part; full lifecycle acceptance remains pending.
- [~] Email and WhatsApp conversation surfaces exist, but unified follow-up orchestration is not complete.

### Phase 5 — Controlled automation and analytics: 50%

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
