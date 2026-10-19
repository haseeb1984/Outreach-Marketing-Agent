# Delivery Roadmap

Implementation is phased. A phase is not complete merely because files exist; automated tests and provider sandbox checks must pass. Frontend quality requirements are defined in docs/QUALITY_STANDARDS.md and are release gates once the UI exists.

## Phase 1 — Foundation
- [x] Initialize repository and product principles.
- [x] Document architecture and compliance requirements.
- [x] Document accessibility, SEO, responsive design, and performance acceptance criteria.
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

## Phase 7 — Frontend, accessibility, SEO and performance
- [ ] Document and agree the frontend stack before substantial UI implementation.
- [ ] Build responsive public marketing pages and authenticated dashboard with semantic HTML and accessible interaction patterns.
- [ ] Meet WCAG 2.2 AA acceptance criteria; run automated accessibility checks and manual keyboard/screen-reader tests.
- [ ] Add technical SEO essentials for intended public pages: metadata, canonical URLs, sitemap, robots rules, correct status codes and accurate structured data where appropriate.
- [ ] Prevent private/dashboard pages from being indexed; ensure authentication and authorization protect private content.
- [ ] Add Lighthouse CI or equivalent repeatable lab checks; investigate regressions and target at least 90 for Performance, Accessibility, SEO and Best Practices on representative pages.
- [ ] Measure Core Web Vitals; target LCP ≤ 2.5 s, INP ≤ 200 ms and CLS ≤ 0.1 at the 75th percentile when field data is available.
- [ ] Verify mobile/tablet/desktop layouts, zoom/reflow, supported browsers and core workflow states.
- Exit: release evidence is recorded per docs/QUALITY_STANDARDS.md; no known critical barriers in core tasks and no critical/high security release blockers.

## Phase 8 — Production hardening
- [ ] Authorization/security review, dependency scanning and backups.
- [ ] Concurrency/load tests, retention/deletion and operational alerts.
- [ ] Deployment, restore and incident runbooks.
- [ ] Validate performance under representative API and background-job load.

## Progress reporting

Report each phase as Done / In progress / Blocked with commit or test evidence. Do not mark mocks as completed integrations. A written standard is not proof of implementation or conformance.
