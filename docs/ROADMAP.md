# Delivery and conversation roadmap

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
- **Production operations:** security review, tenant-isolation review across all resources, accessibility/manual screen-reader checks, performance measurements, backup/restore drill, incident runbook, and legal/policy launch review remain release gates.
- **Analytics:** report only provider-verified sends, delivery, replies, clicks, conversions, and ROI where data exists; do not infer successful external events from local state alone.

## Release rules

1. Work on `main` only; no extra branches.
2. Keep real credentials in encrypted environment/secret storage; never commit or log them.
3. Keep external sending, real payments, and website writes gated until staging acceptance and explicit release approval.
4. CI success verifies only the tested commit and checks; it does not prove production readiness or external provider operation.
