# Launch gap register

Last reviewed: 2026-11-21  
Scope: launch and production-operational acceptance for Outreach Marketing Agent. This is an evidence-based register of the currently identified open workstreams, not a claim that no further defects can be discovered. Reconcile it after each acceptance batch.

## Currently identified open gaps

| ID | Open gap | Current evidence / acceptance needed | Status |
| --- | --- | --- | --- |
| LG-01 | Production database migrations | GitHub Actions migration run `45051010880` completed successfully on `main` commit `583117609d7c69a0148104862c546d9b9294ae86`; backend CI run `45050136091` passed Python 3.11, 3.12 and 3.13. On 2026-11-22, the owner reported that every row in the supplied read-only production SQL verification returned PASS, covering the migration ledger and the listed 057–062 schema checks. The SQL output was not independently captured by this agent. Neon managed backup/PITR is a separate post-deployment operational responsibility and is not a migration or development acceptance criterion. | Migrations applied; owner-reported schema verification PASS |
| LG-02 | Hostinger frontend release | Frontend changes are packaged and CI-tested; Hostinger deployment has not been performed or verified from this agent. Deploy the approved frontend artifact and verify the live domain. | External deployment |
| LG-03 | Platform-owner access configuration | Owner supplied `outreach@juncsys.com`; backend authorization reads `PLATFORM_ADMIN_EMAILS`. On 2026-11-22, the Vercel project environment variable was upserted as a sensitive value for production, preview and development. Runtime authorization is not yet verified because this environment change has not been followed by an approved backend deployment and owner-login acceptance. | Vercel configuration applied; runtime acceptance pending deployment |
| LG-04 | Trusted crawler egress | The current Vercel environment-key inventory did not include `TRUSTED_EGRESS_PROXY_URL`. Configure a trusted egress proxy and verify crawler requests use it. | External infrastructure |
| LG-05 | AI and search provider readiness | The current Vercel environment-key inventory did not include `AI_API_KEY` or `BRAVE_SEARCH_API_KEY`. Configure the providers intended for launch and verify quota, fallback and error behavior. | Provider configuration |
| LG-06 | Central WhatsApp integration | The current Vercel environment-key inventory did not include the central Meta app secret, webhook verify token or Graph API version; outbound remains gated. Configure credentials, webhook verification, consent/template checks and controlled test delivery before enabling. | Provider configuration and acceptance |
| LG-07 | Live billing activation | Current Vercel inventory contains Paddle API-key, webhook-secret and plan-catalog entries, with `PADDLE_ENVIRONMENT=sandbox` and `PADDLE_LIVE_CHECKOUT_ENABLED=false`. This confirms configuration entries only, not valid credentials or a successful sandbox transaction. Complete sandbox checkout/webhook lifecycle acceptance first; production live credentials, live price IDs and explicit activation approval remain unverified. | Sandbox acceptance / live provider approval |
| LG-08 | Persisted plan entitlements | Actual database plan rows may still contain old or incomplete entitlements. Reconcile each plan row against the approved product/quota matrix and verify customer-side enforcement. | Database data validation |
| LG-09 | Worker and scheduler operations | Repository now documents the durable growth worker, recurring growth scheduler, approval-only follow-up worker, fail-closed WhatsApp worker and five-minute GitHub delivery workflow, including install/verification steps and distinct acceptance checks. No live-host service status, alert evidence, end-to-end production processing or lease-recovery drill has been supplied. | Host operations / acceptance |
| LG-10 | Scheduled automation runner reliability | Historical scheduled GitHub workflow failures included jobs that failed before runner allocation (runner ID 0, no steps). Re-establish reliable scheduled execution or move critical schedules to a supervised host scheduler, then evidence successful runs. | External CI infrastructure |
| LG-12 | Frontend reproducibility and browser acceptance | A genuine npm lockfile is still absent. Added a registry-generated lockfile workflow that performs `npm ci`, type-check, production build, smoke tests and browser acceptance before committing the lockfile; the main frontend CI now prefers `npm ci` whenever the lockfile exists. After the repository was made private, the generator run `44947447543` (including retry) and CI runs `44947453221` / `44947453232` failed before any job step was available (`steps: null`); this is a runner-level failure signal, not a test failure or proof of a code defect. The previous verified head `9ef2d11` passed both frontend and backend CI. | Engineering / CI runner availability |
| LG-13 | Jurisdictional retention and financial evidence | Retention periods and legal-hold rules are not approved; sole-member workspace deletion cascades local billing evidence. Decide and implement any required governed financial archive and provider-side deletion/retention schedule before enabling deletion in affected jurisdictions. | Operator/legal decision and implementation |

| LG-14 | SMTP inbox delivery and provider feedback acceptance | Workspace SMTP account lifecycle, test-send and delivery queue exist in code, but no controlled staging outreach delivery, inbox placement, bounce/complaint/unsubscribe webhook or reply-ingestion acceptance is evidenced. Validate with an operator-owned test mailbox and provider relay; do not use a real prospect list. | Provider configuration / staging acceptance |
| LG-15 | Authenticated browser and tenant-isolation acceptance | Added Playwright browser journeys for registration, invalid-login messaging, password-reset request, email-verification token-fragment removal, expired-session redirect, and a successful verified-account login. The successful-login journey loads an authenticated workspace, creates a second workspace through the dashboard, and asserts the `X-CSRF-Token` header on the protected POST. Frontend run `44863190105` passed build/public-route checks and reported 15/16 browser tests passing; the login assertion was subsequently narrowed to the page notice. A later run for the correction (`44863490823`) failed before any job step executed; no test result was produced, and no cause is inferred from the empty step list. Backend run `44863490798` likewise failed before executing steps. The latest head (`933807e0`) also produced frontend run `44863834627` and backend run `44863834394` with failed jobs and no executable step list; this is consistent with runner allocation failure, but the GitHub Actions billing/minutes quota has not been directly inspected. Added HTTP-level coverage exercises member role-escalation denial, non-allowlisted platform-admin denial, and fail-closed behavior when the allowlist is empty. Still required: verify the corrected browser suite in a runner that actually starts, execute these tests against PostgreSQL-backed HTTP staging, and retain a two-tenant staging acceptance record. | Engineering / staging acceptance in progress |
| LG-16 | Account export end-to-end verification | Added a disposable-PostgreSQL integration test that applies the full migration chain, calls the authenticated export endpoint against a real asyncpg pool, and verifies workspace/domain tenant isolation, bounded-export metadata, download/cache security headers and exclusion of password hashes/session-token data. Backend CI run `44862854390` passed all Python 3.11/3.12/3.13 jobs on commit `6a792a0b08b7b69d8f62bfccc59f7b493fe719e5`; the latest backend run `44863190158` also passed all three Python jobs on the current code plus documentation head. A production-like downloaded artifact review and retention/privacy sign-off remain outstanding. | Engineering CI passed; privacy/operator acceptance open |
| LG-17 | Discovery and campaign measurement completeness | The workspace website-growth review already integrates public competitor-candidate discovery, bounded robots-aware competitor page comparison and human-reviewed content-gap evidence. Added a dedicated public influencer-profile discovery endpoint with platform filtering, profile URL validation/deduplication, explainable query relevance and human-review gating. It does not fabricate creator-quality scores or audience metrics. Remaining: provider-backed follower/view/engagement/demographic metrics and verified signup/sale/revenue attribution. Do not infer reach, engagement, conversions, revenue or ROI from search snippets or workflow counts. | Provider-backed creator metrics and attribution engineering / acceptance |
| LG-18 | Security, accessibility, performance and incident exercises | Added global browser security headers (MIME sniffing/frame/referrer/permissions policy), HSTS on production HTTPS, and `no-store` for API responses, with regression tests. Extended Playwright public-page acceptance across all 10 public routes to check document language, exactly one main landmark and primary heading, accessible names for interactive controls, and alt attributes on informative images. This is a semantic accessibility baseline, not a WCAG conformance or screen-reader audit. Independent penetration/security assessment, full automated accessibility review, measured load/performance acceptance and incident-response exercise remain outstanding. | Engineering hardening added; external security / QA / operations acceptance open |

## Post-deployment owner operations (outside development scope)

- Neon managed backup/PITR configuration is the owner's responsibility after production deployment/go-live. It is not application development, a pre-launch engineering gap, a migration prerequisite, or a development-completion blocker. Choose retention and snapshot policy at that time based on the live service, Neon plan and recovery requirements.

## Recently implemented and CI-verified (not counted as open)

- Account deletion lifecycle, deleted-account membership/invitation guards, and tenant cleanup cascades in migrations 060–062.
- Workspace membership/invitation lifecycle locking and audit coverage.
- Backup checksum verification and guarded single-transaction restore.
- This batch: explicit local backup pruning with dry-run default, a configurable age threshold, a minimum retained archive count, symlink/unrelated-file protection, and deletion of matching checksum sidecars only when `--apply` is supplied.
- LG-09 documentation consistency: the growth-worker host runbook now covers the approval-only campaign follow-up service and the separate five-minute GitHub delivery workflow, with explicit checks that follow-up processing creates drafts but does not send.
- LG-16 engineering: added `backend/tests/test_account_export_postgres.py`, which applies the full migration chain on a disposable PostgreSQL database and exercises the actual authenticated account-export endpoint through an asyncpg pool. It checks tenant isolation, exported workspace/domain rows, truncation metadata, security headers and exclusion of password hashes and session tokens. The existing backend CI provisions PostgreSQL and runs DB integration tests on Python 3.12; the test passed in backend CI run `44862854390` across Python 3.11/3.12/3.13. Production-like artifact review and privacy sign-off remain open.

## Backup pruning safety contract

The prune operation does not create a backup, encrypt or replicate it, schedule itself, enforce a legal retention schedule, or prove recoverability. It is deliberately dry-run by default. Do not schedule `--apply` until the retention schedule, off-host recovery copy, legal-hold process and restore rehearsal have been approved and evidenced.

## Counting rule

At this review, **17 distinct open launch workstreams are documented** (LG-01 through LG-10 and LG-12 through LG-18). Post-deployment backup administration is excluded from this engineering/launch-gap count. Some contain multiple acceptance tasks and may split into smaller tracked items after detailed implementation planning. This is the current known count, not a guarantee that a complete code/security/product audit will discover no additional gaps. A gap is closed only when its stated acceptance evidence exists; code merged or CI passing alone does not close production-operations gaps.


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
- Persistent workers and delivery scheduler -> LG-09/LG-10. Neon managed backup/PITR is a separate post-deployment owner operation, not a development gap.
- Frontend lockfile and browser acceptance -> LG-12; retention/legal/financial archive -> LG-13.
- SMTP delivery/inbox and provider-feedback acceptance -> LG-14.
- Authenticated signup/recovery, browser journey, roles and cross-tenant denial -> LG-15.
- Privacy export schema/tenant/output acceptance -> LG-16.
- Incomplete discovery (competitor intelligence) and verified attribution/provider-backed influencer metrics -> LG-17.
- Security assessment, load/performance, accessibility and incident exercise -> LG-18.

The old audit's basic Vercel HTTP smoke checks and earlier backend CI are historical evidence only; they do not certify the current Hostinger frontend, current production schema or provider operations. The public-route Playwright suite added in LG-12 does not satisfy LG-15's authenticated browser journeys. This reconciliation is based on repository documents and CI evidence; it is not a fresh penetration test, production database inspection or external provider test.


## Accessibility baseline progress (2026-11-21)

- Extended the existing public-route Playwright suite with semantic checks across all 10 public routes: document language, one main landmark, one primary heading, accessible names for interactive controls (buttons, links and form fields), and alt attributes on informative images.
- This baseline catches common structural regressions but does not claim WCAG conformance, keyboard-flow completeness, color-contrast validation or screen-reader acceptance.
- The suite has not yet been run on the current head because the recent GitHub Actions jobs failed before runner allocation. LG-18 remains open pending successful browser execution and broader accessibility/performance/security acceptance.


## Influencer discovery implementation (2026-11-21)

- Added `POST /api/v1/research/influencers/search` for authenticated workspace members, with CSRF enforcement and the existing `prospect_research` quota reservation. Added a workspace dashboard form to select platforms, run discovery and review returned public profiles.
- Supports Instagram, TikTok, YouTube, LinkedIn and X public profile candidates. It filters content/search URLs, canonicalizes profile URLs and deduplicates profiles before returning results.
- Results are topical search candidates only. The score is query/title/snippet overlap, not creator quality or influence. Results are not automatically saved to the CRM or contacted.
- Follower counts, average views, engagement rate, audience demographics, conversions, revenue and ROI remain unavailable unless a verified provider/first-party integration supplies them.
- Added profile-shape and mocked endpoint tests. They have not yet run in CI; do not treat implementation tests as verified until the combined test run succeeds. Dashboard integration has not yet been browser-tested.

## Influencer discovery hardening (2026-11-21)

- Tightened creator profile URL validation so LinkedIn in-profile and YouTube channel/custom/user candidates must resolve to profile-shaped paths, not nested post/video/content paths.
- Added backend regression tests for nested content-path rejection, quota-denied provider suppression and fail-closed behavior when Brave Search is not configured.
- Added an authenticated Playwright dashboard journey covering selected-platform submission, CSRF header, idempotency key and the explicit audience-metrics-unavailable state.
- Corrected dashboard URL assertions in the authenticated browser suite while extending it.
- These new backend and browser tests have been authored but have **not** been executed on the current head. Do not count them as CI-verified until a runner completes them.

## Influencer search input validation (2026-11-21)

- Normalize workspace identifiers and creator-search queries by trimming surrounding whitespace; reject values that become blank before quota reservation or provider requests.
- Normalize platform selections, remove duplicates and preserve only supported platform identifiers.
- Added schema regression coverage for whitespace normalization, blank query/workspace rejection and duplicate platform selection.
- Tests are authored but remain pending the combined CI run; no verification status is inferred.

- Canonicalized legacy `twitter.com` creator links to the same `x.com` profile URL so cross-domain duplicates collapse during discovery.


## X/Twitter discovery coverage (2026-11-21)

- Expanded X creator discovery queries to include both `x.com` and the legacy `twitter.com` host. Returned Twitter profile URLs are still normalized to canonical X URLs and deduplicated with matching X-host results.
- Extended the mocked discovery endpoint regression test to assert both search domains are queried and a legacy Twitter result is returned as a canonical X profile. Tests remain pending successful CI execution.

- Follow-up regression coverage now supplies the same X creator through both `twitter.com` and `x.com`; the endpoint must return one canonical profile, not two separate candidates.


## Accessibility reference integrity progress (2026-11-21)

- Extended the public-route semantic browser check to validate every token in `aria-labelledby` against an existing element ID. This catches controls that appear labelled in markup but resolve to no accessible-name source.
- This remains a structural regression check; it does not replace computed accessible-name inspection, keyboard testing, contrast checks or screen-reader review. The current-head suite has not been executed.


- Hardened the `aria-labelledby` regression check: it now tokenizes references on actual whitespace (rather than a literal backslash sequence) and also rejects duplicate element IDs, which can make accessible-name references ambiguous. This check remains pending current-head browser execution.


## Current private-repository CI and deployment checkpoint (2026-11-22)

- GitHub repository visibility is now private (verified from the repository API).
- On the last fully verified code head `9ef2d113298250c0a27a3b3a67bf2d29533272ba`, Backend CI and Hostinger Frontend CI both passed, including the three-version Python matrix, frontend type-check/build/smoke checks and Playwright browser acceptance.
- Subsequent CI attempts on `5ac1858`, `b91cf95`, `a25d8fb` and `7cb15ff` failed before any job steps were available. The job payloads returned `steps: null`; no test command ran, so the cause cannot be attributed to code. The latest Backend CI run is `44950129541` and Frontend CI run is `44950129521`. Owner-side GitHub Actions billing/runner access must be restored before the tests can execute.
- Latest Vercel production deployment remains on `main` commit `58fd1622e6ec2c5d9911174d9ac56c33a15ec7ed`; the launch-readiness PR branch is not deployed to production. No production deployment or database migration was performed.
- Vercel runtime error aggregation returned no runtime error clusters for the inspected 24-hour window. This is not a full end-to-end production acceptance test.


- Added [Owner Activation Checklist](OWNER_ACTIVATION_CHECKLIST.md) with the exact non-secret owner inputs, missing Vercel environment keys, Paddle sandbox/live gates, migration approvals, and GitHub Actions recovery steps. It explicitly prohibits sharing secrets in chat and separates customer-owned SMTP from platform configuration.

## Current branch verification checkpoint (2026-11-22)

- PR #89 head `140ffe382505411cf56ee6d75d38af4b3a1eb48d` completed Backend CI and Hostinger Frontend CI successfully (workflow runs `44970828384` and `44970828410`).
- Backend CI completed the Python 3.11, 3.12 and 3.13 test jobs successfully, including the PostgreSQL-backed test environment.
- Frontend CI completed TypeScript checking, the production build, production-server smoke tests, and all 19 Playwright browser tests successfully. The browser run includes six authenticated journeys, influencer discovery, all 10 public routes, semantic accessibility-baseline checks and the mobile homepage viewport check.
- The frontend workflow also generated a CI ZIP artifact. This is not a release approval and does not close the external launch gaps below; no Hostinger upload, production migration, production deployment, live billing activation, WhatsApp activation or real outreach was performed by this verification.
- The npm lockfile remains absent from the branch, so the CI install still uses the workflow's non-lockfile fallback. LG-12 remains open for reproducible dependency installation despite the successful current CI run.
- The passing mocked/authenticated browser journeys do not replace PostgreSQL-backed HTTP staging with two real tenants, provider acceptance, or production operations evidence. LG-01 through LG-11 and LG-13 through LG-18 remain open until their stated acceptance evidence exists.


## LG-01 production migration execution checkpoint (2026-11-22)

- GitHub Actions run `45051010880` completed successfully. Its job log records migrations `057_core_outreach_tenant_integrity.sql` through `062_followup_resolution_tenant_cleanup.sql` as applied, using the `DATABASE_URL` secret.
- The run checked out `main` at `583117609d7c69a0148104862c546d9b9294ae86`. The workflow source contains no backup step, and the run has no uploaded artifacts. This is historical context only; Neon managed backups are configured independently after deployment and are not required for development or migration acceptance.
- Backend CI run `45050136091` passed all three matrix jobs (Python 3.11, 3.12 and 3.13) on the same commit.
- On 2026-11-22, the owner ran the supplied read-only SQL verification against production and reported **all checks PASS**. The checks covered the `schema_migrations` ledger and the specified columns, indexes, foreign keys/delete actions, constraints and functions for migrations 057–062. The result is owner-reported; no raw result export or screenshot was supplied to this agent.
- Neon managed backup/PITR retention is intentionally not an LG-01 migration acceptance item. The owner will configure and verify it independently after deployment/go-live; retention duration will be selected then based on the Neon plan and recovery requirements.
- No application deployment was performed as part of this migration run.
