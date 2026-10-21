# Delivery Roadmap

Implementation is phased. A phase is not complete merely because files exist; automated tests and provider sandbox checks must pass. Frontend quality requirements are defined in docs/QUALITY_STANDARDS.md. Commercial SaaS requirements are defined in docs/SAAS_PLATFORM_REQUIREMENTS.md. Written requirements are not proof of implementation.

## Product priority rule

The first release must prioritize four core workflows: (1) client/business discovery and qualification, (2) personalized email and official WhatsApp outreach, (3) competitor-aware SEO strategy, and (4) safe website crawlability/SEO diagnosis plus verified improvement. Paid ads, social publishing, video, advanced PR, reputation, advanced CRO, and other channels are optional add-ons. Do not expand optional channels while core workflows remain unimplemented or untested.

SEO work must target measurable competitive improvement: baseline target queries/pages, inspect observable competitor evidence, apply prioritized client-approved improvements, re-crawl, and measure outcomes using authorized data. The 90–95% improvement ambition is not a universal guarantee; report actual performance honestly and never fabricate rankings or causality.

## Phase 1 — Foundation
- [x] Initialize repository and product principles.
- [x] Document architecture and compliance requirements.
- [x] Document accessibility, SEO, responsive design, and performance acceptance criteria.
- [x] Document commercial SaaS, tenant isolation, billing, and entitlement requirements.
- [x] Runnable FastAPI health endpoint and environment-backed configuration.
- [x] Automated tests and CI (GitHub Actions green on Python 3.11/3.12/3.13; PostgreSQL integration and pip-audit passed in run #371).
- [x] Database schema and explicit migration workflow.
- Exit: clean install, app starts, tests pass, CI is green, no secrets committed.

## Phase 2 — Identity and SaaS foundation
- [ ] Select and document frontend stack and deployment architecture.
- [x] Implement customer registration, email verification, login/logout, password reset, session expiry/revocation.\n- [ ] Account deletion/export workflows.
- [ ] Implement workspaces/tenants, memberships, roles, invitations, and server-side object authorization.
- [x] Add database migrations and tenant-aware access patterns for workspace membership and prospect CRM.\n- [ ] Complete tenant-aware data access for every remaining resource type.
- [x] Add authentication rate limits and security event audit logs.\n- [ ] Complete secret-management integration, baseline monitoring and account recovery hardening.
- [ ] Add automated cross-tenant authorization tests for every resource type.
- Exit: identity and tenant boundaries are tested; no cross-tenant leakage or critical/high security blockers.

## Phase 3 — Product discovery
- [ ] Multi-project CRUD and tenant boundaries.
- [ ] Website analysis with SSRF protections.
- [ ] Optional analysis of repositories the user is authorized to access.
- [ ] Source-backed features, benefits, pricing and audience profile.

## Phase 4 — Core client discovery, competitor intelligence and CRM
- [ ] Approved public-source search adapters for business/client discovery and prospect research.
- [ ] Profile the client's actual offer, audience, market, goals and approved outreach criteria.
- [ ] Discover relevant competing businesses/pages and compare observable search intent, content coverage, crawlability and available authority evidence.
- [ ] Evidence URL, observation date, fit score and discovery reason for each lead and competitor finding.
- [ ] Deduplication, human review, CRM stages, notes, and campaign membership.
- [ ] Enforce workspace/project scope for all prospect data.

## Phase 5 — Core personalized outreach (email and WhatsApp)
- [ ] Multiple connected email accounts with project scoping and secure token storage/revocation.
- [ ] Official WhatsApp Business Platform integration where eligible; never unofficial WhatsApp Web automation.
- [ ] Business- and prospect-specific messages grounded in verified facts, fit reason, offer and context; avoid generic bulk templates.
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

## Phase 10 — Core competitive SEO and website growth engine
- [ ] Add per-workspace client/business profiles, authorized domains, audience/market/language goals, budget caps, conversion goals and brand guidelines.
- [ ] Build a safe read-only website audit with SSRF-safe fetching, bounded crawl, and evidence-backed technical SEO/indexability findings.
- [ ] Audit each authorized client's robots.txt, XML sitemaps, canonicalization, internal links, metadata, structured data, mobile usability, accessibility and performance.
- [ ] Add AI/search crawler readiness checks, optional /llms.txt recommendations, factual entity consistency and evidence-based AI search content guidance.
- [ ] Implement competitor-aware technical SEO and crawlability priorities, search-intent/content gap analysis, and repeatable before/after verification as core workflows.
- [ ] Treat AEO/GEO and other modern channels as optional/secondary modules unless they directly support the client's agreed core goals.
- [ ] Keep digital PR, local/e-commerce specialists, social/community, paid acquisition, reputation, video, advanced CRO and retention optional and opt-in.
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

## Verified implementation snapshot — 2026-10-20

This snapshot records shipped backend service components, not phase completion. The full phases above remain open until their listed acceptance criteria are met.

### Phase 10 — website discovery and SEO growth foundation
- **Implemented and CI-tested:** `backend/app/services/website_audit.py` parses supplied HTML into evidence-linked observations without making network requests.
- **Implemented and CI-tested:** `backend/app/services/website_fetch.py` provides bounded HTTP retrieval, public-address validation, restricted redirects, response-size/time limits, and text-document retrieval for trusted callers. DNS validation separated from connection establishment does not fully eliminate rebinding races.
- **Implemented and CI-tested:** `backend/app/services/website_crawler.py` performs bounded same-host, source-HTML crawling and aggregates observations. It can honor supplied robots rules and same-host seed URLs.
- **Implemented and CI-tested:** `backend/app/services/robots_sitemap.py` parses robots.txt and sitemap XML, and evaluates common Allow/Disallow path patterns. It is not a complete implementation of every crawler's robots behavior.
- **Implemented and CI-tested:** `backend/app/services/website_discovery.py` fetches robots.txt and bounded same-host sitemap documents, then orchestrates the crawl. Unexpected robots retrieval/validation failures fail closed.
- **Implemented and CI-tested:** `backend/app/services/website_growth_report.py` and `backend/app/services/website_growth_pipeline.py` compose crawl findings into evidence-backed, human-reviewable strategy actions. When safe discovery is skipped, the pipeline emits no strategy actions.
- **CI evidence:** [website discovery/growth pipeline run](https://github.com/haseeb1984/Outreach-Marketing-Agent/actions/runs/39323836566) passed on 2026-10-20, including Python 3.11, 3.12 and 3.13 test jobs; dependency audit passed in the Python 3.12 job.
- **Implemented and CI-tested (security primitives only):** `backend/app/services/domain_authorization.py` normalizes domain names, issues short-lived DNS TXT challenges, verifies supplied TXT answers against a stored token hash, and authorizes exact-host URLs only when a matching active verified-domain record belongs to the requesting workspace. The raw TXT token is separated from the persistable challenge metadata.
- **Implemented and CI-tested (service-level gate):** `backend/app/services/website_growth_pipeline.py` now requires a workspace ID and verified-domain records and checks the exact host/workspace match before calling network discovery. Tests assert unverified and cross-workspace domains are rejected before any fetch. The caller must still obtain workspace identity from real authentication and load domain records from trusted persistent storage; the current app does not yet provide those integrations.
- **Still not implemented/production-ready:** challenge/domain persistence and migration, an authoritative DNS TXT lookup adapter, authenticated user/workspace resolution, transactional verification and replay protection, domain-management API/UI, quotas and queueing, connection-pinned egress proxy protection against DNS rebinding, JavaScript rendering, PageSpeed/field-data integrations, comprehensive accessibility/performance/security checks, competitor-data acquisition, authorized analytics baselines, before/after measurement, public authenticated API wiring, and any automated site changes. These are not represented as complete.
- **Release restriction:** these service functions are not a public unauthenticated crawl API. Production exposure requires tenant authorization, abuse controls, per-workspace quotas, and stronger network egress enforcement first.

### Current core workflow status
- **Website crawlability/SEO diagnosis:** foundational read-only services implemented; broader feature coverage and production safety remain in progress.
- **Evidence-based SEO strategy:** standalone strategy builder and crawl-report composition implemented; real competitor research and authorized performance data remain unimplemented.
- **Business/prospect discovery and CRM:** not yet a complete integrated workflow.
- **Email and official WhatsApp outreach:** evidence-based draft generation exists; provider connections, persistent approvals, suppression enforcement at send time, and live delivery are not complete.
- **Commercial SaaS:** authentication, tenant isolation, billing, durable queueing, frontend dashboard, and production launch gates remain outstanding.

## Progress reporting

Report each phase as Done / In progress / Blocked with commit or test evidence. Do not mark mocks as completed integrations. A written standard is not proof of implementation or conformance.
