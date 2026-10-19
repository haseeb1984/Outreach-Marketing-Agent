# Delivery Roadmap

Implementation is phased. A phase is not complete merely because files exist; automated tests and provider sandbox checks must pass. Frontend quality requirements are defined in docs/QUALITY_STANDARDS.md. Commercial SaaS requirements are defined in docs/SAAS_PLATFORM_REQUIREMENTS.md. Written requirements are not proof of implementation.

## Phase 1 — Foundation
- [x] Initialize repository and product principles.
- [x] Document architecture and compliance requirements.
- [x] Document accessibility, SEO, responsive design, and performance acceptance criteria.
- [x] Document commercial SaaS, tenant isolation, billing, and entitlement requirements.
- [ ] Runnable FastAPI health endpoint and configuration.
- [ ] Automated tests and CI.
- [ ] Database schema and migration workflow.
- Exit: clean install, app starts, tests pass, CI is green, no secrets committed.

## Phase 2 — Identity and SaaS foundation
- [ ] Select and document frontend stack and deployment architecture.
- [ ] Implement customer registration, email verification, login/logout, password reset, session expiry/revocation, and account deletion/export.
- [ ] Implement workspaces/tenants, memberships, roles, invitations, and server-side object authorization.
- [ ] Add database migrations and tenant-aware data access patterns.
- [ ] Add rate limits, security event audit logs, secret management, and baseline monitoring.
- [ ] Add automated cross-tenant authorization tests for every resource type.
- Exit: identity and tenant boundaries are tested; no cross-tenant leakage or critical/high security blockers.

## Phase 3 — Product discovery
- [ ] Multi-project CRUD and tenant boundaries.
- [ ] Website analysis with SSRF protections.
- [ ] Optional analysis of repositories the user is authorized to access.
- [ ] Source-backed features, benefits, pricing and audience profile.

## Phase 4 — Prospect research and CRM
- [ ] Approved public-source search adapters.
- [ ] Evidence URL, observation date, fit score and discovery reason for each lead.
- [ ] Deduplication, human review, CRM stages, notes, and campaign membership.
- [ ] Enforce workspace/project scope for all prospect data.

## Phase 5 — Provider accounts and outreach drafting
- [ ] Multiple connected email accounts with project scoping and secure token storage/revocation.
- [ ] Official WhatsApp Business Platform integration where eligible.
- [ ] Evidence-grounded personalized drafts and approval queue.
- [ ] Reply synchronization/classification and human handoff.
- [ ] Opt-out/suppression enforcement before every send and follow-up.

## Phase 6 — Billing, plans and usage entitlements
- [ ] Confirm merchant eligibility, launch jurisdictions, supported currencies, fees and payment provider before production integration.
- [ ] Implement hosted checkout/provider adapter and signed, idempotent webhook processing.
- [ ] Model plans, entitlements, subscription lifecycle, cancellations, failed payments, refunds, and reconciliation.
- [ ] Enforce entitlements and usage quotas server-side on every paid operation and queued job.
- [ ] Implement atomic quota reservations and concurrency/race tests.
- [ ] Add customer billing/usage UI, invoices/receipts where supported, and clear cancellation/support policies.
- [ ] Verify that forged redirects, client plan tampering, duplicate/out-of-order webhooks, and cross-tenant billing access cannot grant or expose access.
- Exit: provider sandbox lifecycle tests pass; real payments remain disabled until security, merchant, policy and operational checks pass.

## Phase 7 — Controlled automation and analytics
- [ ] Explicit opt-in, sending limits, quiet hours, retries and kill switch.
- [ ] Idempotent queue jobs and duplicate-send protection.
- [ ] Re-check entitlements, quotas, account status, and suppression rules at send time.
- [ ] Track only verifiable delivery, reply, click, signup and sales events.

## Phase 8 — Frontend, accessibility, SEO and performance
- [ ] Build public marketing, pricing, policy, registration, account, workspace, dashboard, billing, and support pages.
- [ ] Meet WCAG 2.2 AA; run automated accessibility checks and manual keyboard/screen-reader tests.
- [ ] Add technical SEO essentials for intended public pages: metadata, canonical URLs, sitemap, robots rules, correct status codes and accurate structured data where appropriate.
- [ ] Prevent private/dashboard/account/billing pages from being indexed; authentication must protect private content.
- [ ] Add Lighthouse CI or equivalent repeatable lab checks; target at least 90 for Performance, Accessibility, SEO and Best Practices on representative pages.
- [ ] Measure Core Web Vitals; target LCP ≤ 2.5 s, INP ≤ 200 ms and CLS ≤ 0.1 at the 75th percentile when field data is available.
- [ ] Verify mobile/tablet/desktop layouts, zoom/reflow, supported browsers, payment flows, and error/recovery states.
- Exit: release evidence recorded per docs/QUALITY_STANDARDS.md; no critical barriers in core tasks and no critical/high security blockers.

## Phase 9 — AI discoverability and self-marketing
- [ ] Publish server-rendered/crawlable public marketing, pricing, product, documentation, FAQ, changelog and policy pages with accurate metadata and canonical URLs.
- [ ] Add and validate sitemap.xml and robots.txt; ensure neither exposes private data or blocks required public assets.
- [ ] Publish and maintain /llms.txt as a helpful public documentation index, without assuming every AI crawler supports it.
- [ ] Add accurate structured data only where visible content supports it; prohibit fabricated reviews, ratings, feature claims and statistics.
- [ ] Add approved content planning and drafting based on verified features, evidence, user questions and measured demand.
- [ ] Implement factual claim checks, broken-link checks, SEO/accessibility checks, human approval, version history, scheduling, rollback and a marketing kill switch.
- [ ] Add privacy-respecting analytics for organic discovery, qualified signups, activation and conversions; connect official webmaster tools only with user authorization.
- [ ] Test crawler access to public routes and verify private/authenticated routes remain inaccessible to anonymous crawlers and other tenants.
- [ ] Ensure promotion channels use authorized integrations and respect anti-spam requirements, opt-outs, provider limits and explicit automation consent.
- Exit: public crawlability and marketing workflow have recorded tests; no claim is made that AI platforms will index or recommend the product.

## Phase 10 — Per-client website growth and modern marketing engine
- [ ] Add per-workspace client/business profiles, authorized domains, audience/market/language goals, budget caps, conversion goals and brand guidelines.
- [ ] Build a safe read-only website audit with SSRF-safe fetching, bounded crawl, and evidence-backed technical SEO/indexability findings.
- [ ] Audit each authorized client's robots.txt, XML sitemaps, canonicalization, internal links, metadata, structured data, mobile usability, accessibility and performance.
- [ ] Add AI/search crawler readiness checks, optional /llms.txt recommendations, factual entity consistency and evidence-based AI search content guidance.
- [ ] Implement strategy selection and prioritization across technical SEO, content/topic authority, AEO/GEO, digital PR, local SEO, e-commerce, social/community, email lifecycle, partnership/influencer outreach, authorized paid acquisition, CRO, analytics, reputation, video and retention.
- [ ] Require evidence, baseline, confidence, effort/cost, KPI, approval state and outcome tracking for recommendations.
- [ ] Add channel-by-channel authorization, human approval, quota/budget limits, opt-outs, provider policy checks, audit trail, rollback where feasible and emergency kill switch.
- [ ] Build client reporting that distinguishes observed, calculated, estimated, recommended, completed and unknown outcomes.
- [ ] Test tenant isolation, ownership verification, write/publish/spend/send approval gates, suppression, rate limits, crawl bounds and non-fabricated reporting.
- Exit: core supported marketing workflow passes recorded tests; unsupported integrations are explicitly labelled planned or unavailable.

## Phase 11 — Production hardening and launch
- [ ] Authorization/security review, dependency scanning and backups.
- [ ] Concurrency/load tests, retention/deletion and operational alerts.
- [ ] Payment webhook reconciliation, billing/support runbooks, backup restore and incident drills.
- [ ] Verify provider terms, messaging/email compliance, privacy/terms pages, customer support and merchant requirements.
- [ ] Staging-to-production checklist, rollback plan, monitoring and first-customer support readiness.
- Exit: all release gates and required evidence pass; no mock integration represented as live.

## Progress reporting

Report each phase as Done / In progress / Blocked with commit or test evidence. Do not mark mocks as completed integrations. A written standard is not proof of implementation or conformance.
