# Launch gap register

Last reviewed: 2026-11-19  
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

## Recently implemented and CI-verified (not counted as open)

- Account deletion lifecycle, deleted-account membership/invitation guards, and tenant cleanup cascades in migrations 060–062.
- Workspace membership/invitation lifecycle locking and audit coverage.
- Backup checksum verification and guarded single-transaction restore.
- This batch: explicit local backup pruning with dry-run default, a configurable age threshold, a minimum retained archive count, symlink/unrelated-file protection, and deletion of matching checksum sidecars only when `--apply` is supplied.
- LG-09 documentation consistency: the growth-worker host runbook now covers the approval-only campaign follow-up service and the separate five-minute GitHub delivery workflow, with explicit checks that follow-up processing creates drafts but does not send.

## Backup pruning safety contract

The prune operation does not create a backup, encrypt or replicate it, schedule itself, enforce a legal retention schedule, or prove recoverability. It is deliberately dry-run by default. Do not schedule `--apply` until the retention schedule, off-host recovery copy, legal-hold process and restore rehearsal have been approved and evidenced.

## Counting rule

At this review, **13 distinct open launch workstreams are documented (LG-01 through LG-13)**. Some contain multiple acceptance tasks and may split into smaller tracked items after detailed implementation planning. This is the current known count, not a guarantee that a complete code/security/product audit will discover no additional gaps. A gap is closed only when its stated acceptance evidence exists; code merged or CI passing alone does not close production-operations gaps.


## Frontend browser acceptance progress (2026-11-19)

- Added `@playwright/test`, `frontend/playwright.config.ts` and `frontend/e2e/public-site.spec.ts`.
- Browser suite checks all 10 public routes return HTTP 200 and expected content, detects uncaught browser page errors, and checks the homepage does not overflow a 390px mobile viewport.
- Frontend CI installs Chromium and runs the browser suite against the built production server after the existing HTTP smoke suite.
- A committed `frontend/package-lock.json` is still not present. Local registry DNS is unavailable, and no lockfile was fabricated. LG-12 remains open until a genuine lockfile is generated and CI/Hostinger installation is switched to `npm ci`.
- No production deployment was performed.
