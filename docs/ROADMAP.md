# Delivery and conversation roadmap

Percentages represent verified implementation scope, not launch readiness. A phase is complete only after its acceptance checks pass. See [Implementation status and release blockers](IMPLEMENTATION_STATUS.md) for the current evidence-based matrix.

## Current implementation update — 2026-11-24

- Current implementation source on `main`: `523e9e91c253105bca3fcd13a03f0f606d486551`. This is a source-control reference, not a CI or deployment claim.
- Added a persistent editorial pipeline from website-growth recommendations to workspace content briefs, editorial review, AI-generated SEO article drafts, editable metadata/body, and article approval.
- Added project-workflow dashboard loading so saved briefs survive refreshes and workspace switches.
- Added project-scoped WordPress Application Password storage (with a workspace-default fallback) encrypted with AES-GCM, HTTPS/public-DNS checks, connection verification, and permission checks for authoring/publishing.
- Approved articles can be transferred to WordPress as drafts. Draft retries recover/update the same post; article revisions can be resubmitted and synchronized to an existing WordPress draft.
- Public publishing is a separate admin-only action with explicit browser confirmation and server-side confirmation. No automatic CMS publishing occurs.
- WordPress disconnection revokes the stored encrypted credential while preserving the connection record and linked post history.
- Added the missing CORS PUT allowance required by the dashboard's WordPress connection-save endpoint. Editing an article that already has a WordPress draft now marks the CMS copy out-of-sync and blocks publishing until the updated article is resynchronized.
- Completed customer self-service account privacy controls in the dashboard: download a bounded JSON export (including saved editorial articles and non-secret WordPress connection metadata) and request irreversible account deletion with explicit confirmation, session revocation, identity pseudonymization, and shared-workspace ownership safeguards.
- Added migrations `065`–`068`, backend routes/services, dashboard controls and WordPress operations documentation.
- WordPress connections can now be scoped to individual client projects, with an optional workspace-default fallback. New article transfers prefer a verified project connection; the saved CMS connection ID pins retries and publishing to the original site. Existing workspace connections remain intact as the fallback.
- **Not yet verified:** these latest editorial/CMS changes have not been built or tested, migrations have not been confirmed applied to a live database, WordPress staging credentials/provider acceptance have not been exercised, and no Hostinger frontend ZIP/upload or production deployment has occurred.
- Earlier CI and deployment records below apply only to the commits they explicitly identify; they do not validate this newer implementation.

## Earlier verified baseline — 2026-11-24

- Historical application CI baseline: `dd9a499baaf8989cbf4d11531f6882d54ba1cd16`.
- Backend CI passed on this exact SHA: [run 45295962702](https://github.com/haseeb1984/Outreach-Marketing-Agent/actions/runs/45295962702).
- Hostinger Frontend CI passed on this exact SHA: [run 45295962678](https://github.com/haseeb1984/Outreach-Marketing-Agent/actions/runs/45295962678), including type-check, production build, smoke tests, Playwright browser acceptance and Hostinger source-ZIP packaging.
- Vercel production deployment record is READY on this exact SHA. It is the FastAPI backend deployment and does not establish that the separately hosted Hostinger frontend has been uploaded.
- Dashboard controls and endpoint wiring include projects, workspace settings/members, invitations, account export, domain verification, read-only website audits, prospect research review, analytics, integration status, SMTP connection test and delivery-provider event history. The dashboard's current static route test checks rendered UI and wiring; each workflow still needs authenticated database/provider acceptance.
- Account export/deletion and workspace ownership-transfer APIs exist in source; lifecycle and authorization acceptance remain required.
- Project API has an optional disposable-PostgreSQL lifecycle test for create/list/update/archive and cross-workspace denial. It runs only when `OMA_TEST_DATABASE_URL` is configured; do not infer that it ran from the general CI success badge.
- **Billing:** Paddle checkout, customer portal and webhook/lifecycle foundations exist; sandbox checkout, portal, signed webhook delivery, subscription reconciliation and entitlements acceptance remain pending.
- **WhatsApp:** Meta inbound webhook/account/conversation, consent and outbound-queue policy foundations exist; the outbound dispatcher and live sending remain unaccepted and disabled.
- **Email:** durable outbound queue and SMTP adapter foundations exist; staging SMTP inbox delivery and deliverability monitoring remain unverified.
- **Current release gates:** live authenticated customer journey; database-backed lifecycle and tenant-isolation acceptance; SMTP staging delivery; Paddle sandbox lifecycle; Meta staging acceptance and outbound dispatcher; backup restore drill; accessibility/performance; and monitoring/incident readiness.


> The older phase descriptions below are historical snapshots. Where they say billing or WhatsApp has not been implemented at all, use the dated status above: foundations have since been added, but external acceptance and release readiness remain pending.

Percentages represent verified implementation scope, not launch readiness. A phase is complete only after its acceptance checks pass. See [Implementation status and release blockers](IMPLEMENTATION_STATUS.md) for the current evidence-based matrix.

## Implemented foundations (automated tests pass; external operation still needs staging verification)

- Authentication/session and CSRF foundations, workspace roles, rate-limiting foundations, and PostgreSQL-backed identity.
- Workspace-scoped prospect/CRM operations, campaign records, evidence-aware draft generation, explicit human review, and contact controls.
- Durable outbound delivery queue with workspace isolation, per-draft uniqueness, idempotency keys, explicit admin send actions, and send-time approval/suppression checks.
- TLS-only SMTP adapter and safe integration-status diagnostics. Configuration presence is not proof that provider authentication or inbox delivery works.
- Provider-neutral signed inbound-reply webhook with bounded payloads, validation, event deduplication, persistence, and conversation history.
- Read-only website discovery/audit/growth-report services with domain-authorization and SSRF/egress guardrails.
- Responsive same-origin `/app` dashboard wired to authenticated APIs: registration/sign-in, active workspace selection, prospect and campaign creation/listing, draft review, and read-only delivery activity. UI actions respect workspace roles; automated route tests and JavaScript syntax validation pass.
- Public marketing HTML routes, canonical/robots/sitemap helpers, readiness checks, and AI-discoverability requirements.

## Deferred: WhatsApp Business Platform

WhatsApp is intentionally **PENDING** while Meta account setup and same-number Coexistence eligibility are unresolved. Do not delete or deregister the existing WhatsApp Business App number. No live WhatsApp sends are enabled.

Still required before connecting Meta: eligible Coexistence onboarding, provider-specific GET verification handshake, raw-body `X-Hub-Signature-256` validation, native payload normalization, workspace/phone asset mapping, durable inbound/status event persistence, idempotency, official outbound adapter, opt-in/template checks, and staging acceptance. Configuration-status output is diagnostic only.

## Remaining product and launch work

- **Dashboard extensions:** workspace/project settings, invitations, account export/deletion UI, connected-provider management, and a full browser-based onboarding journey remain incomplete. The current dashboard is a functional core foundation, not a claim that the entire SaaS is launch-ready.
- **Subscriptions and paid entitlements:** billing provider selection, hosted checkout, signed/idempotent billing webhooks, server-side entitlements, atomic quotas, subscription lifecycle, and reconciliation remain incomplete.
- **Research integrations:** live search/provider adapters, provider account connections, evidence capture at scale, and production analytics require implementation and staging verification.
- **Email release verification:** actual encrypted staging SMTP configuration, provider-authenticated smoke test, deliverability evidence, and operational alerts have not been verified from this repository review.
- **Pre-launch production gates:** security review, tenant-isolation review across all resources, accessibility/manual screen-reader checks, performance measurements, incident runbook, and legal/policy launch review remain release gates. **Post-deployment operations:** the owner configures Neon managed backup/PITR retention and snapshot policy after go-live, selects retention based on the live service's recovery objectives and Neon plan, and verifies restore readiness; track this separately from migration acceptance.
- **Analytics:** report only provider-verified sends, delivery, replies, clicks, conversions, and ROI where data exists; do not infer successful external events from local state alone.

## Release rules

1. Work on `main` only; no extra branches.
2. Keep real credentials in encrypted environment/secret storage; never commit or log them.
3. Keep external sending, real payments, and website writes gated until staging acceptance and explicit release approval.
4. CI success verifies only the tested commit and checks; it does not prove production readiness or external provider operation.
