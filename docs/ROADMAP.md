# Delivery Roadmap

Each phase has explicit exit criteria. A phase is not complete just because files exist; tests and integration checks must pass.

## Phase 1 — Repository and application foundation
- [x] Establish project principles and technical direction.
- [x] Define architecture, compliance guardrails, and delivery gates.
- [ ] Add runnable FastAPI health endpoint and configuration validation.
- [ ] Add automated tests and CI.
- [ ] Define initial database schema and migration workflow.
- Exit criteria: clean install, app starts, health test passes, CI is green, no secrets committed.

## Phase 2 — Website/GitHub product discovery
- [ ] Project CRUD and tenant/project boundaries.
- [ ] Website metadata and page analysis with SSRF protections.
- [ ] Optional GitHub analysis only for repositories the user is authorized to access.
- [ ] Structured product profile: features, benefits, pricing evidence, audiences, positioning.
- Exit criteria: source-backed outputs, safe URL validation, repeatable tests.

## Phase 3 — Public prospect research and qualification
- [ ] Search-provider abstraction and approved public sources.
- [ ] Prospect schema with evidence URL, observed date, fit score, and rationale.
- [ ] Deduplication, confidence levels, review and exclusion controls.
- Exit criteria: no lead can be saved as qualified without traceable evidence and a reason.

## Phase 4 — CRM and integrations
- [ ] Prospect stages, notes, tasks, campaign membership.
- [ ] Multiple OAuth-connected email accounts with project scoping.
- [ ] Official WhatsApp Business Platform integration, only where account/API eligibility is satisfied.
- [ ] Secure credential storage, revocation, health status and reconnect flows.
- Exit criteria: provider sandbox tests; secrets never appear in logs or API responses.

## Phase 5 — Drafting, approvals and reply management
- [ ] Personalized drafts grounded in product profile and prospect evidence.
- [ ] Approval queue and immutable audit trail.
- [ ] Reply ingestion/classification, opt-out/suppression, human handoff.
- [ ] Sending disabled by default until a provider integration is explicitly configured and tested.
- Exit criteria: approval is required before any send in the initial release; opt-outs suppress future messages.

## Phase 6 — Controlled automation and analytics
- [ ] Explicit per-project automation enablement and daily/hourly limits.
- [ ] Eligibility checks, quiet hours, retry policies and kill switch.
- [ ] Track delivery, replies, clicks, signups and sales only when supported by actual events/integrations.
- [ ] ROI calculation with documented attribution assumptions.
- Exit criteria: simulated and sandbox tests, duplicate-send protection, complete audit trail.

## Phase 7 — Production hardening and release
- [ ] Threat model, authorization review, dependency scanning and backups.
- [ ] Load/concurrency tests, retention/deletion flows, operational alerts.
- [ ] Deployment, migration, restore and incident-response runbooks.
- [ ] Human review of messaging and privacy compliance.
- Exit criteria: release checklist signed off; unresolved critical/high findings block release.

## Progress reporting
For every phase, report **Done / In progress / Blocked**, evidence (commit/test/run), and remaining work. Never mark an integration complete based solely on mocks.
