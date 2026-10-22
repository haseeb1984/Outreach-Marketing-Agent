# Architecture

## Product model
This is a commercial multi-tenant SaaS platform, not a single-user utility. Customers register, create a workspace, invite authorized teammates, connect their own provider accounts, choose a subscription, and use only the features and quotas granted by server-verified entitlements. Payment status, plan entitlements, tenant isolation, security, and auditability are core architecture requirements.

## Components
1. **Hostinger Business frontend:** Next.js + TypeScript + Tailwind public marketing site, pricing/FAQ/policies, account entry points, and responsive authenticated dashboard. Hostinger is the frontend host, not Vercel.
2. **FastAPI backend on Vercel:** authentication, authorization, validation, tenant-aware business rules, billing adapter, entitlements, and provider adapters. The frontend calls it over HTTPS and never connects directly to the database.
3. PostgreSQL as the durable source of truth for users, workspaces, memberships, projects, prospects, campaigns, messages, account metadata, subscriptions, billing events, usage reservations, suppression records, and audit events.
4. PostgreSQL as the durable source of truth for users, workspaces, memberships, projects, prospects, campaigns, messages, account metadata, subscriptions, billing events, usage reservations, suppression records, and audit events.
5. Durable worker/queue for research, AI, synchronization, billing reconciliation, and sending jobs, with idempotency, retries, cancellation, quotas, and per-account/project limits.
6. Provider adapters for website fetch, authorized GitHub reads, search, LLM, email, official WhatsApp Business Platform, payment/billing, and analytics events.
7. Security layer for tenant isolation, session security, encrypted secrets, audit events, rate limits, retention, monitoring, abuse prevention, and incident response.

## Tenant and authorization boundaries
- Model a workspace/tenant as the customer boundary; membership and role are checked server-side on every request and job.
- Never trust a tenant/workspace/user/resource ID supplied by the client without verifying membership and object-level authorization.
- Enforce isolation in service/repository queries and, where feasible, reinforce it with database constraints or row-level security.
- Test cross-tenant access for every customer-owned resource: projects, prospects, messages, reports, integrations, billing records, usage, and exports.
- Encrypt provider tokens at rest; never return them to the browser after connection.
- Store only public-source prospect details needed for legitimate professional contact.
- Check suppression/opt-out immediately before every send and follow-up.
- Administrative/support access is least-privilege and audited.

## Identity, billing and entitlements
- Authentication must include secure registration, verification, sign-in/out, password reset, session expiry/revocation, and account deletion/export.
- A verified payment-provider event updates durable subscription state through a signed, idempotent webhook handler. Browser redirects are never proof of payment.
- Billing provider choice must be validated for merchant eligibility and launch jurisdiction before production integration.
- Never store raw card numbers or CVV. Use hosted checkout or approved tokenization.
- Every paid API operation and queued job re-checks subscription entitlement, quota, workspace status, and applicable safety checks on the server.
- Quota reservation and consumption must be atomic under concurrency; a frontend plan label is not authorization.
- Failed billing verification fails closed for paid actions, with a recoverable customer-facing message.
- Reconcile subscription state with the payment provider and alert on discrepancies.

## Data and workflows
### Product discovery
User submits website and optional authorized repository → validate target/access and enforce SSRF controls → fetch only public or authorized material → extract structured facts with evidence → user reviews profile → approved profile grounds campaign drafts.

### Prospect research
Campaign definition → search permitted public sources → normalize/deduplicate candidates → attach evidence URL and observation date → calculate transparent fit score and discovery reason → user reviews candidates → approved prospects enter CRM.

### Outreach
Eligible prospect and product profile → generate evidence-grounded draft → check policy, suppression, subscription entitlement, quota and duplicates → human approval → queued provider send with idempotency key and limits → persist provider result → sync/classify replies → suggest follow-up or human handoff.

### Billing
Customer starts hosted checkout → provider processes payment → signed webhook is validated and deduplicated → subscription state and entitlements are persisted transactionally → UI reads server-confirmed state → recurring webhook/reconciliation updates state → cancellation/refund/failure follows the documented policy. Never unlock paid access based solely on the return URL.

### Analytics
Ingest verifiable provider and user-supplied conversion events → reconcile by campaign/prospect → report metrics and attribution assumptions. Never fabricate delivery, clicks, sales or ROI.

## Reliability and operations
- External calls use timeouts, bounded retries and rate limits.
- Queue jobs are idempotent and persist state transitions; retries must not cause duplicate sends or duplicate charges.
- Secrets and personal data are redacted from logs.
- Schema changes use versioned migrations.
- Sending jobs re-check suppression, eligibility, subscription, limits and account health at execution time.
- Use separate development/staging/production configurations, backups and restore drills, monitoring, alerts, and incident runbooks.
- Keep payment events and security-sensitive actions auditable; define data retention and deletion behavior before launch.


## Public discoverability and responsible self-marketing
- Keep a public, crawlable website/documentation surface separate from the authenticated application and private APIs.
- Generate sitemap and robots rules from an explicit allowlist of canonical public routes; do not include account, dashboard, customer, lead, billing, report or private API URLs.
- Maintain /llms.txt as a concise index of authoritative public product documentation; do not treat it as an authentication mechanism or guarantee of AI crawler adoption.
- The optional marketing service consumes verified product capability records, approved sources and aggregate performance data. It creates draft content with evidence references and marks uncertain claims for review.
- Publishing runs through a policy/quality gate: validate claims against actual shipped features, check links, metadata, duplicate/doorway patterns, accessibility, consent and channel-specific limits. Initial publishing requires human approval.
- Keep publication permissions, schedules, revisions, rollback, audit logs, per-channel quotas and an emergency kill switch. Marketing automation cannot override unsubscribe/suppression records or provider restrictions.
- Store public content and customer-specific marketing drafts with different access controls. Never expose private leads, connected-account data, campaign details, secrets, billing records or customer reports to public crawlers.
- Measure discovery and conversion with privacy-respecting analytics. Report measured evidence, not promised rankings, AI citations, or guaranteed growth.


## Core competitive growth workflows
- Core value is client/business discovery, business-specific email and official WhatsApp outreach, competitor intelligence, and measurable website crawlability/SEO improvement. Other marketing channels are optional add-ons.
- Client discovery captures verified business facts, audience, market, offer, target customers, and constraints; prospect and competitor results require source evidence, observation timestamps, deduplication, and transparent fit/priority reasons.
- Competitor analysis is limited to observable public pages and authorized data. It compares search intent, content coverage, technical crawlability, internal structure, user experience, and external authority evidence where available; it must not claim knowledge of private ranking algorithms.
- SEO optimization follows a baseline → evidence-backed diagnosis → prioritized client-approved changes → re-crawl/re-test → performance measurement loop. Ranking goals are measured for defined query sets and time windows; no fixed uplift is guaranteed or fabricated.

## Per-client website growth and modern marketing
- Each workspace can own separate client/business profiles and explicitly authorized domains. Store goals, markets/languages, audience, brand constraints, budgets, approved channels, baseline metrics, and authorization evidence.
- The website audit service is read-only by default. It uses SSRF-safe fetch/crawl controls and returns evidence-backed observations, not unsupported assumptions.
- A strategy orchestrator must prioritize core business discovery, competitor-aware technical/content SEO, and personalized email/official WhatsApp outreach. Other modules (AEO/GEO enhancements, digital PR, local/e-commerce specialists, social/community, paid acquisition, advanced CRO, reputation, video and retention) are optional and selected only when relevant.
- Strategy decisions consume verified client facts, authorized analytics, current audit evidence, explicit goals and resource limits. Each recommendation records sources, date, confidence, impact hypothesis, effort/cost, KPI, risk and approval state.
- Execution connectors are separate from planning. Website writes, CMS publishing, DNS changes, ad spend, emails, social posting and external messages require scoped authorization and configurable approval. Quotas, suppression, provider policies, idempotency, audit history and a kill switch apply at execution time.
- Analytics distinguishes observed, calculated, estimated, recommended, completed and unknown results; no invented traffic, rankings, citations, leads or ROI.
- Public crawler endpoints and the client's public website content are not granted access to workspace data, customer credentials, lead records, campaign drafts or private reports. Tenant isolation and object-level authorization apply to every request and job.
- Full specification and acceptance criteria: docs/CLIENT_WEBSITE_GROWTH_ENGINE.md.

## Quality gates
- Follow docs/QUALITY_STANDARDS.md for WCAG 2.2 AA, technical SEO, responsive design, and Core Web Vitals.
- Follow docs/SAAS_PLATFORM_REQUIREMENTS.md for customer accounts, subscription billing, entitlements, quotas, tenant isolation, payment security, and launch tests.
- Follow docs/SAFETY_AND_COMPLIANCE.md for outreach safety, privacy, and SSRF.
- A mock is not a production integration. Do not accept real payments until sandbox tests, security checks, merchant eligibility, policies, support and reconciliation are verified.
