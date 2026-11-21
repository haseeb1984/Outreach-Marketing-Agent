# Launch gap register

Last reviewed: 2026-11-21  
Scope: launch and production-operational acceptance for Outreach Marketing Agent. This is an evidence-based register of the currently identified open workstreams, not a claim that no further defects can be discovered. Reconcile it after each acceptance batch.

## Currently identified open gaps

| ID | Open gap | Current evidence / acceptance needed | Status |
| --- | --- | --- | --- |
| LG-01 | Production database migrations | Migrations 057–062 are in the release preflight and CI, but have not been applied to production. Apply only through the approved migration process after a fresh backup and migration plan. | Operator approval / production action |
| LG-02 | Hostinger frontend release | Frontend changes are packaged and CI-tested; Hostinger deployment has not been performed or verified from this agent. Deploy the approved frontend artifact and verify the live domain. | External deployment |
| LG-03 | Platform-owner access configuration | Vercel environment inventory previously showed `PLATFORM_ADMIN_EMAILS` absent. Configure the authorized owner allowlist and verify admin access without broadening privileges. | Environment configuration |
| LG-04 | Trusted crawler egress | `TRUSTED_EGRESS_PROXY_URL` was absent from the inspected Vercel environment inventory. Configure a trusted egress proxy and verify crawler requests use it. | External infrastructure |
| LG-05 | AI and search provider readiness | `AI_API_KEY` and `BRAVE_SEARCH_API_KEY` were absent in the inspected environment inventory. Configure only the providers intended for launch and verify quota, fallback and error behavior. | Provider configuration |
| LG-06 | Central WhatsApp integration | Meta app secret, webhook verify token and Graph API version were absent; outbound remains gated. Configure credentials, webhook verification, consent/template checks and controlled test delivery before enabling. | Provider configuration and acceptance |
| LG-07 | Live billing activation | Paddle live API credentials, webhook secret and live price IDs were absent; live checkout remains disabled. Complete live catalog mapping, webhook verification, idempotency and test transactions before activation. | Provider configuration and acceptance |
| LG-08 | Persisted plan entitlements | Actual database plan rows may still contain old or incomplete entitlements. Reconcile each plan row against the approved product/quota matrix and verify customer-side enforcement. | Database data validation |
| LG-09 | Worker and scheduler operations | Repository now documents the durable growth worker, recurring growth scheduler, approval-only follow-up worker, fail-closed WhatsApp worker and five-minute GitHub delivery workflow, including install/verification steps and distinct acceptance checks. No live-host service status, alert evidence, end-to-end production processing or lease-recovery drill has been supplied. | Host operations / acceptance |
| LG-10 | Scheduled automation runner reliability | Historical scheduled GitHub workflow failures included jobs that failed before runner allocation (runner ID 0, no steps). Re-establish reliable scheduled execution or move critical schedules to a supervised host scheduler, then evidence successful runs. | External CI infrastructure |
| LG-11 | Backup and disaster-recovery operations | Code supports custom-format backups, SHA-256 verification and atomic restore; this batch adds dry-run-first local retention pruning. No verified remote encrypted copy, approved expiry schedule, successful production archive or separate-environment restore rehearsal is available. | Operator policy / infrastructure / drill |
| LG-12 | Frontend reproducibility and browser acceptance | Frontend CI type-check/build/HTTP smoke tests pass. A Playwright Chromium suite now covers 10 public routes, browser runtime errors and mobile homepage horizontal overflow; CI installs Chromium and runs it after the production build. A committed npm lockfile is still absent, so dependency resolution is not yet reproducible and this gap remains open. | Engineering / CI |
| LG-13 | Jurisdictional retention and financial evidence | Retention periods and legal-hold rules are not approved; sole-member workspace deletion cascades local billing evidence. Decide and implement any required governed financial archive and provider-side deletion/retention schedule before enabling deletion in affected jurisdictions. | Operator/legal decision and implementation |

| LG-14 | SMTP inbox delivery and provider feedback acceptance | Workspace SMTP account lifecycle, test-send and delivery queue exist in code, but no controlled staging outreach delivery, inbox placement, bounce/complaint/unsubscribe webhook or reply-ingestion acceptance is evidenced. Validate with an operator-owned test mailbox and provider relay; do not use a real prospect list. | Provider configuration / staging acceptance |
| LG-15 | Authenticated browser and tenant-isolation acceptance | Added Playwright browser journeys for registration, invalid-login messaging, password-reset request, email-verification token-fragment removal, expired-session redirect, and a successful verified-account login. The successful-login journey loads an authenticated workspace, creates a second workspace through the dashboard, and asserts the `X-CSRF-Token` header on the protected POST. Frontend run `44863190105` passed build/public-route checks and reported 15/16 browser tests passing; the login assertion was subsequently narrowed to the page notice. A later run for the correction (`44863490823`) failed before any job step executed; no test result was produced, and no cause is inferred from the empty step list. Backend run `44863490798` likewise failed before executing steps. The latest head (`933807e0`) also produced frontend run `44863834627` and backend run `44863834394` with failed jobs and no executable step list; this is consistent with runner allocation failure, but the GitHub Actions billing/minutes quota has not been directly inspected. Added HTTP-level coverage exercises member role-escalation denial, non-allowlisted platform-admin denial, and fail-closed behavior when the allowlist is empty. Still required: verify the corrected browser suite in a runner that actually starts, execute these tests against PostgreSQL-backed HTTP staging, and retain a two-tenant staging acceptance record. | Engineering / staging acceptance in progress |
| LG-16 | Account export end-to-end verification | Added a disposable-PostgreSQL integration test that applies the full migration chain, calls the authenticated export endpoint against a real asyncpg pool, and verifies workspace/domain tenant isolation, bounded-export metadata, download/cache security headers and exclusion of password hashes/session-token data. Backend CI run `44862854390` passed all Python 3.11/3.12/3.13 jobs on commit `6a792a0b08b7b69d8f62bfccc59f7b493fe719e5`; the latest backend run `44863190158` also passed all three Python jobs on the current code plus documentation head. A production-like downloaded artifact review and retention/privacy sign-off remain outstanding. | Engineering CI passed; privacy/operator acceptance open |
| LG-17 | Discovery and campaign measurement completeness | The project scorecard still records deeper competitor intelligence, dedicated influencer discovery/scoring and verified campaign/revenue attribution as incomplete. Confirm the accepted product scope, implement any required workflows, and do not display unverified attribution/ROI. | Product scope / engineering |
| LG-18 | Security, accessibility, performance and incident exercises | No current evidence of an independent penetration/security assessment, load/performance acceptance, accessibility/screen-reader review or incident-response exercise. Run scoped assessments, fix release-blocking findings and record measured results before launch. | Security / QA / operations |

## Recently implemented and CI-verified (not counted as open)

- Account deletion lifecycle, deleted-account membership/invitation guards, and tenant cleanup cascades in migrations 060–062.
- Workspace membership/invitation lifecycle locking and audit coverage.
- Backup checksum verification and guarded single-transaction restore.
- This batch: explicit local backup pruning with dry-run default, a configurable age threshold, a minimum retained archive count, symlink/unrelated-file protection, and deletion of matching checksum sidecars only when `--apply` is supplied.
- LG-09 documentation consistency: the growth-worker host runbook now covers the approval-only campaign follow-up service and the separate five-minute GitHub delivery workflow, with explicit checks that follow-up processing creates drafts but does not send.
- LG-16 engineering: added `backend/tests/test_account_export_postgres.py`, which applies the full migration chain on a disposable PostgreSQL database and exercises the actual authenticated account-export endpoint through an asyncpg pool. It checks tenant isolation, exported workspace/domain rows, truncation metadata, security headers and exclusion of password hashes and session tokens. The existing backend CI provisions PostgreSQL and runs DB integration tests on Python 3.12; this new test is awaiting its workflow result.

## Backup pruning safety contract

The prune operation does not create a backup, encrypt or replicate it, schedule itself, enforce a legal retention schedule, or prove recoverability. It is deliberately dry-run by default. Do not schedule `--apply` until the retention schedule, off-host recovery copy, legal-hold process and restore rehearsal have been approved and evidenced.

## Counting rule

At this review, **18 distinct open launch workstreams are documented (LG-01 through LG-18)**. Some contain multiple acceptance tasks and may split into smaller tracked items after detailed implementation planning. This is the current known count, not a guarantee that a complete code/security/product audit will discover no additional gaps. A gap is closed only when its stated acceptance evidence exists; code merged or CI passing alone does not close production-operations gaps.


## Frontend browser acceptance progress (2026-11-19)

- Added `@playwright/test`, `frontend/playwright.config.ts` and `frontend/e2e/public-site.spec.ts`.
- Browser suite checks all 10 public routes return HTTP 200 and expected content, detects uncaught browser page errors, and checks the homepage does not overflow a 390px mobile viewport.
- Frontend CI installs Chromium and runs the browser suite against the built production server after the existing HTTP smoke suite.
- A committed `frontend/package-lock.json` is still not present. Local registry DNS is unavailable, and no lockfile was fabricated. LG-12 remains open until a genuine lockfile is generated and CI/Hostinger installation is switched to `npm ci`.
- No production deployment was performed.


## Original production-audit reconciliation (2026-11-19)

The 2026-10-23 production smoke audit was reconciled against the current source/CI evidence and the 2026-11-01 project progress scorecard. Findings are tracked as follows:

- Production schema/migration acceptance -> LG-01; Hostinger release -> LG-02; platform-owner allowlist -> LG-03.
- Crawler egress -> LG-04; AI/search provider readiness -> LG-05; Meta/WhatsApp acceptance -> LG-06; Paddle lifecycle -> LG-07; persisted entitlement data -> LG-08.
- Persistent workers and delivery scheduler -> LG-09/LG-10; backup/restore -> LG-11.
- Frontend lockfile and browser acceptance -> LG-12; retention/legal/financial archive -> LG-13.
- SMTP delivery/inbox and provider-feedback acceptance -> LG-14.
- Authenticated signup/recovery, browser journey, roles and cross-tenant denial -> LG-15.
- Privacy export schema/tenant/output acceptance -> LG-16.
- Incomplete discovery (competitor intelligence, influencer scoring) and verified attribution -> LG-17.
- Security assessment, load/performance, accessibility and incident exercise -> LG-18.

The old audit's basic Vercel HTTP smoke checks and earlier backend CI are historical evidence only; they do not certify the current Hostinger frontend, current production schema or provider operations. The public-route Playwright suite added in LG-12 does not satisfy LG-15's authenticated browser journeys. This reconciliation is based on repository documents and CI evidence; it is not a fresh penetration test, production database inspection or external provider test.
