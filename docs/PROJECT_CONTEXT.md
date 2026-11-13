# Outreach Marketing Agent — Project Context

> Source-based product map reconciled against the repository implementation-status and roadmap documents on 2026-11-13. CI and code inventory are not proof of external provider or production acceptance.

## Purpose
Multi-tenant SaaS for business-aware prospect discovery, CRM, personalized email outreach, WhatsApp Business inbound foundations, competitor intelligence, website crawlability/SEO growth, human approvals and subscription entitlements.

## Stack and dependencies
- Backend: FastAPI / Python; backend/requirements.txt.
- Frontend: Next.js 15, React 19, TypeScript; frontend/package.json.
- Persistence: PostgreSQL / asyncpg with checked-in migrations.
- Background processing: durable delivery queue, webhook processing and website-growth worker/scheduler architecture.
- External systems: LLM, search, SMTP/ESP, Meta WhatsApp Business Platform and Paddle; source code presence does not prove provider acceptance.
- Intended deployment: Hostinger Business frontend, Vercel FastAPI backend, and a separately supervised persistent worker host. Verify current live configuration before release.

## Architecture
- Customer uses the same-origin Next.js workspace dashboard.
- FastAPI applies identity, session, CSRF, workspace-role and entitlement checks.
- CRM/campaign services connect to prospect discovery, draft generation and read-only website-growth services.
- Approved email drafts enter the durable idempotent queue and TLS SMTP adapter.
- Signed feedback/reply events update delivery state, conversations and suppression records.
- Meta webhook intake and bounded workers process inbound WhatsApp events into workspace-scoped conversations; outbound sending is disabled.
- Billing and entitlement foundations persist provider events and usage; paid release remains gated on provider acceptance and transactional enforcement.
- PostgreSQL is the shared persistence layer; background work runs through durable queue/worker infrastructure.

## Main workflows
1. Customer registers, signs in and selects an authorized workspace.
2. Workspace users create prospects and campaigns; discovery and audit services collect public, authorized evidence.
3. Agent generates evidence-grounded outreach drafts; users edit, approve or reject them.
4. Approved email sends enter a durable queue with send-time approval and suppression checks.
5. Signed inbound replies and ESP feedback update conversations, delivery state and suppression records.
6. Meta webhook events can be verified, mapped to a workspace account and processed into inbound CRM conversations; outbound WhatsApp sending remains disabled.
7. Website growth scans are read-only and run through durable worker infrastructure.
8. Paddle catalog, signed event and entitlement foundations exist; paid release remains gated on merchant/provider acceptance and complete transactional enforcement.

## Feature inventory
See FEATURES.md for the detailed register covering identity/workspaces, CRM, campaign and draft approval, email queue/SMTP/reply/feedback foundations, WhatsApp inbound/consent/queue boundaries, website growth, public discoverability, platform administration and billing/entitlement foundations.

## Roadmap and gaps
See ROADMAP.md and GAPS.md. These are reconciled with the existing implementation-status and roadmap references so implemented capabilities are not repeated as future work. External provider acceptance and launch blockers remain separate from implemented source capabilities.

## Source-of-truth rules
- Keep docs/IMPLEMENTATION_STATUS.md as the evidence-based implementation and release matrix.
- Keep docs/ROADMAP.md as the canonical product/release roadmap.
- Distinguish checked-in implementation, passing automated tests, deployed service and externally accepted provider workflow; these are different statuses.
- Never claim outbound WhatsApp sending is enabled; it remains disabled.
- Never claim paid billing is production-ready until Paddle lifecycle acceptance and transactional quota/entitlement enforcement are complete.
- Do not describe read-only website audits as automatic website modifications.
