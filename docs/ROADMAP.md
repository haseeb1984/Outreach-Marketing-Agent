# Delivery and conversation roadmap

Percentages represent verified implementation scope, not launch readiness. A phase is complete only after its acceptance checks pass. See [Implementation status and release blockers](IMPLEMENTATION_STATUS.md) for the current evidence-based matrix.

## Current verified update — 2026-11-24

- Current `main` HEAD: `85b9ce0b93040722fbeb13de0c9d2020bf6af592`.
- Backend CI passed on that exact HEAD: [run 45251520483](https://github.com/haseeb1984/Outreach-Marketing-Agent/actions/runs/45251520483), with Python 3.11/3.12/3.13 jobs.
- Frontend CI last verified on `91febc4af4f6d278fa7e8f49afafe48ad3b11622`: [run 45114987413](https://github.com/haseeb1984/Outreach-Marketing-Agent/actions/runs/45114987413). Type-check, production build, smoke tests and browser acceptance passed there; this is not a frontend pass for current HEAD.
- Authenticated Playwright coverage includes account registration/login/recovery, workspace selection and creation with CSRF, session expiry, email verification and influencer discovery/review. These tests stub API responses and do not establish production account or external-provider acceptance.
- **Billing:** Paddle checkout/customer-portal and webhook/lifecycle foundations are present in code. Sandbox checkout, portal, webhook delivery, subscription lifecycle and reconciliation still require end-to-end acceptance. Do not label billing production-ready.
- **WhatsApp:** Meta inbound webhook/account/conversation foundations plus consent and outbound-queue policy foundations are present. The outbound dispatcher and live sending are not accepted; Meta onboarding, live webhook delivery, templates/consent enforcement and staging tests remain gates. Live sends stay disabled.
- **Email:** durable outbound queue and SMTP adapter foundations are present. Authenticated staging SMTP and actual inbox delivery remain unverified.
- **Dashboard:** core authenticated workspace, CRM, campaign/review and delivery workflows exist. Workspace/project settings, invitations, connected-provider management, full billing UX, export/deletion UX and complete onboarding remain incomplete.
- **Current release gates:** frontend CI on current HEAD, live authenticated production journey, provider sandbox/staging acceptance, tenant-isolation/security review, accessibility/performance checks, monitoring/incident runbook and backup/restore drill.

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
