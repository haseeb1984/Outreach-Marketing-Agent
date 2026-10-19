# Delivery Roadmap

Implementation is phased. A phase is not complete merely because files exist; automated tests and provider sandbox checks must pass.

## Phase 1 — Foundation
- [x] Initialize repository and product principles.
- [x] Document architecture and compliance requirements.
- [ ] Runnable FastAPI health endpoint and configuration.
- [ ] Automated tests and CI.
- [ ] Database schema and migration workflow.
- Exit: clean install, app starts, tests pass, CI is green, no secrets committed.

## Phase 2 — Product discovery
- [ ] Multi-project CRUD and tenant boundaries.
- [ ] Website analysis with SSRF protections.
- [ ] Optional analysis of repositories the user is authorized to access.
- [ ] Source-backed features, benefits, pricing and audience profile.

## Phase 3 — Prospect research
- [ ] Approved public-source search adapters.
- [ ] Evidence URL, observation date, fit score and discovery reason for each lead.
- [ ] Deduplication and human review.

## Phase 4 — CRM and accounts
- [ ] Prospect stages, notes and campaign membership.
- [ ] Multiple connected email accounts with project scoping.
- [ ] Official WhatsApp Business Platform integration where eligible.
- [ ] Encrypted credentials, revocation and reconnect flows.

## Phase 5 — Drafting and replies
- [ ] Evidence-grounded personalized drafts and approval queue.
- [ ] Reply synchronization/classification and human handoff.
- [ ] Opt-out/suppression enforcement before every send.

## Phase 6 — Controlled automation and analytics
- [ ] Explicit opt-in, sending limits, quiet hours, retries and kill switch.
- [ ] Idempotent queue jobs and duplicate-send protection.
- [ ] Track only verifiable delivery, reply, click, signup and sales events.

## Phase 7 — Production hardening
- [ ] Authorization/security review, dependency scanning and backups.
- [ ] Concurrency/load tests, retention/deletion and operational alerts.
- [ ] Deployment, restore and incident runbooks.

## Progress reporting
Report each phase as Done / In progress / Blocked with commit or test evidence. Do not mark mocks as completed integrations.