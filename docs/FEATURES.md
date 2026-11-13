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

## Additional implemented workflows recorded in implementation history

The following capabilities are also present in the repository implementation history and are included here so the feature register is not limited to the initial module summaries. Their current runtime/database acceptance must still be checked against the release matrix:

### Prospect research and CRM handoff
- Public research-result handoff to the CRM form, pre-filling title, source URL and description while company and website remain user-verified fields.
- Workspace-scoped prospect creation and management; research evidence is retained as context rather than silently treating inferred company details as verified.

### Campaign and draft lifecycle
- Workspace-member campaign editing for name, offer, target profile and lifecycle status.
- Campaign pause/archive enforcement at draft generation, email enqueue and send claim; paused or archived campaigns cannot create or dispatch new outreach.
- Pending-approval draft editing with email subject/body validation, row locking and an activity event recording the edit.
- Saved growth-review reports retain project identity and can be reopened from audit history.

### Website growth engine
- End-to-end code workflow: workspace-authorized project lookup, verified project-domain requirement, website-audit entitlement reservation, bounded crawl, persistence of evidence-led strategy, and dashboard presentation of cited actions plus a measurement plan.
- The workflow is a read-only audit/strategy experience; it does not autonomously publish website changes.

### Paddle billing experience
- Canonical Paddle route supports plan listing, workspace-authorized hosted checkout and customer-portal session creation, alongside signed subscription webhook ingestion and server-side plan/price association.
- Checkout and portal UI controls are present in the dashboard.
- These are implemented integration surfaces, not proof of live merchant eligibility, configured sandbox credentials, successful payment lifecycle, production reconciliation or release-ready paid entitlements.

### Platform administration and operational recovery
- Platform-admin client inventory, feature-usage history and audit-event views with bounded server-side pagination and totals; client search is explicitly scoped to the loaded page where documented.
- Workspace-admin WhatsApp webhook-event visibility, bounded workspace-scoped processing and dead-letter retry controls; these operate on inbound event processing only and never send outbound messages.
- Workspace-admin recovery action can move stale ambiguous email sends to an operator-visible uncertain state without automatic retry.
- Bounded reconciliation utility for stale WhatsApp quota reservations is present; it is an operational script and must not be treated as a continuously running worker unless separately scheduled and verified.

### Deployment packaging and CI
- Backend, frontend, migration and scheduled delivery workflow definitions are checked in.
- A PowerShell Hostinger frontend source-packaging script is present; its existence does not prove that a ZIP has been built, uploaded or accepted on the live Hostinger environment.

## Important implementation boundaries
- WhatsApp outbound queue records eligible send intents only; no dispatcher sends WhatsApp messages.
- Generic ESP feedback/reply endpoints require provider-native signature verification and normalization by the relay/provider integration; generic SMTP itself does not supply mailbox synchronization or delivery webhooks.
- Website growth is read-only. No autonomous site publishing is implemented in the documented workflow.
- Paddle checkout, portal and webhook code remain gated on actual sandbox/provider acceptance and complete transactional entitlement enforcement.
- A source file, migration, CI pass or historical implementation note is not evidence that a live database has applied the migration or that an external provider is operating.
