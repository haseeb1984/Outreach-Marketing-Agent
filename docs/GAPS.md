# Outreach Marketing Agent — Gaps and Release Verification

> Records unfinished scope and external acceptance gates without reclassifying implemented foundations as missing.

## Product and dashboard gaps
1. Workspace/project settings, team invitations and complete account export/deletion UI remain incomplete.
2. Connected-provider management and a complete customer-facing onboarding journey remain incomplete.
3. Live prospect/search provider adapters, evidence capture at scale and production research analytics remain incomplete.
4. Full customer-facing campaign workflow and authenticated production browser acceptance remain to be verified.
5. Competitor and website-growth results need verified provenance, timestamps and first-party outcome measurements.

## Email release gates
- Configure encrypted staging SMTP credentials and run provider-authenticated smoke tests.
- Verify actual inbox delivery, deliverability monitoring and operational alerts.
- Validate provider-native feedback signatures through the configured ESP relay.
- Preserve fail-safe handling for uncertain sends; do not auto-retry ambiguous outcomes.

## WhatsApp boundaries
- Native webhook intake, workspace account mapping, inbound event processing, inbox and consent/policy foundations exist.
- Live Meta business/account/number/webhook acceptance remains pending.
- Outbound draft queue records intent only. No sender dispatches WhatsApp messages; live outbound sending remains disabled.
- Before enabling a sender, verify official Meta onboarding, approved templates, 24-hour service-window enforcement, revocable account-scoped consent, opt-out suppression, durable idempotency, rate/entitlement checks, retries and provider reconciliation.
- Preserve the existing WhatsApp Business App number; do not deregister or migrate it merely to force onboarding.

## Billing and paid access
- Paddle catalog, signed event mapping, entitlement persistence and admin foundations exist.
- Merchant eligibility, hosted checkout and full subscription lifecycle need sandbox/provider acceptance.
- Verify signed webhook handling, idempotent event processing, cancellation/failed-payment lifecycle and reconciliation.
- Paid operations must remain fail-closed until quota/entitlement enforcement is transactional and race-tested across all paid actions and jobs.

## Infrastructure, security and quality gates
- Verify PostgreSQL migrations and tenant isolation across API routes, background jobs, exports and CRM resources.
- Verify deployment environment parity across Hostinger frontend, Vercel backend and persistent worker host.
- Complete persistent supervised-worker deployment and operational acceptance.
- Complete separate-database backup/restore drill, monitoring, incident response and rollback acceptance.
- Complete accessibility/manual screen-reader, performance/load, privacy/legal and production security reviews.
- Run current CI and staging acceptance; historical scorecards and old run links are not substitutes for current verification.

## Status language
Use Implemented foundation, Provider acceptance pending, Partially implemented, Not implemented and Production verification pending precisely. A config variable, checked-in adapter, passing unit test or successful CI run does not prove an external service is live or production-ready.
