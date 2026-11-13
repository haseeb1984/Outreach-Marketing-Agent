# Outreach Marketing Agent — Implemented Feature Register

> Distinguishes source-implemented foundations from external provider acceptance and unfinished product scope. Not a fresh test or production verification report.

## Identity, workspaces and access
- FastAPI/Python backend, Next.js 15 / React 19 / TypeScript frontend and PostgreSQL persistence.
- User registration, sign-in, session and password-reset foundations.
- CSRF/session protections and rate-limiting foundations.
- Multi-tenant workspaces, memberships, workspace roles and server-side authorization checks.
- Same-origin responsive /app dashboard, active-workspace selector and role-aware controls.
- Workspace/project settings, team invitations and full account export/deletion UX remain incomplete.

## CRM, prospect discovery and campaigns
- Workspace-scoped prospect records, CRM operations and contact controls.
- Evidence-aware prospect qualification and draft generation foundations.
- Campaign creation/listing and workspace-scoped campaign records.
- Evidence-grounded template generation and optional OpenAI-compatible Chat Completions generation.
- Draft regeneration with CTA variation and quota accounting.
- Draft editing, approval/rejection with notes and activity timeline.
- Human approval remains the default; draft generation does not send messages.
- Live research-provider adapters, evidence capture at scale and production analytics remain incomplete.

## Email delivery and reply handling
- Workspace SMTP identity management foundation: encrypted credentials, verify-before-activate, diagnostic email, credential rotation and disable controls.
- Durable outbound email queue with workspace isolation, per-draft uniqueness and idempotency keys.
- Explicit admin send actions and send-time approval/suppression checks.
- TLS-only SMTP adapter.
- Ambiguous delivery outcomes move to uncertain state and are not automatically retried.
- Delivery correlation and RFC 8058 one-click unsubscribe headers.
- Unsubscribe, hard-bounce and complaint events persist suppression and cancel queued messages.
- Signed normalized ESP feedback webhook foundation for delivery/deferred/bounce/complaint states.
- Signed normalized inbound-reply webhook foundation with bounds, validation, deduplication, persistence and conversation history.
- Actual staging SMTP inbox delivery, deliverability monitoring and provider-native mailbox synchronization remain unverified/incomplete.

## WhatsApp Business Platform
- Meta webhook verification handshake, raw-body HMAC signature validation, bounded intake and deduplicated event inbox.
- Workspace WhatsApp account registry with admin authorization, encrypted tokens, disable/credential retirement and Graph API verification.
- Optional normalized E.164 prospect phone field.
- Tenant-scoped conversation, inbound-message and delivery-status persistence.
- Event processor maps active phone-number IDs to workspaces, deduplicates provider IDs and records inbound/status events.
- Workspace-scoped inbox and bounded webhook processing/recovery controls.
- Account-scoped consent evidence, opt-out records and fail-closed template/24-hour-window policy evaluator.
- Outbound WhatsApp draft queue records eligible send intents only.
- No outbound dispatcher exists; actual WhatsApp sending remains disabled. Live Meta account/number/webhook acceptance remains pending.

## Website growth and SEO
- Read-only website discovery, audit and growth-report services.
- Domain authorization and SSRF/egress guardrails.
- Durable website-growth worker and scheduler architecture with operational runbooks.
- Live search-provider adapters, authorized first-party analytics and measured outcome integrations remain incomplete.
- Current documented site-growth services are read-only; do not imply autonomous website publishing.

## Billing and platform administration
- Billing/entitlement schema, usage persistence and provider-event ledger foundations.
- Paddle package catalog/admin create-edit-deactivate controls, plan import and audit history.
- Signed Paddle subscription-event mapping with strict provider price/plan association.
- Authenticated read-only entitlement endpoint.
- Platform-admin dashboard foundations: client/subscription overview, feature usage, usage history, paginated audit history and allowlisted access.
- Hosted checkout, merchant eligibility, full subscription lifecycle, reconciliation and transactional paid-operation enforcement remain partial/unverified. Paid access must remain fail-closed until accepted.

## Public site and operational foundations
- Public marketing routes: home, product, pricing, FAQ, privacy, terms and contact.
- robots.txt, sitemap.xml, llms.txt and public discoverability helpers.
- Dashboard supports registration/sign-in, workspace selection, prospect/campaign create/list, draft review and read-only delivery activity.
- Private dashboard pages use noindex/no-store and security headers.
- PostgreSQL migrations, readiness checks, CI workflows, automated backend/frontend tests and dependency audit evidence.
- Production runbooks cover worker hosting, backup/restore, monitoring, incident response, rollback and launch acceptance.

## Status rules
- CI passing proves only the checks run for the recorded commit; it does not prove production deployment or provider acceptance.
- WhatsApp outbound sending is disabled.
- Paddle paid access is not production-ready until provider lifecycle acceptance and complete transactional enforcement are verified.
- Read-only website audits are not automatic website modifications.
