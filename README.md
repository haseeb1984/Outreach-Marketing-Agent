# Outreach Marketing Agent

A commercial, multi-tenant SaaS platform whose core job is to help client businesses win more qualified opportunities and improve organic search performance through business-aware prospect discovery, personalized email/WhatsApp outreach, competitor intelligence, and website crawlability/SEO optimization. Customers will be able to register, manage isolated workspaces/projects, research public-facing prospects and competing pages, draft personalized outreach, track replies and SEO outcomes, and pay for plan-based access.

## Product principles

- **Research before outreach:** every lead should include a public source/evidence URL, fit score, and concise reason for inclusion.
- **Human approval first:** outreach is drafted for review by default. Any later automation must be explicitly enabled, rate-limited, auditable, and subject to eligibility checks.
- **Respectful, compliant contact:** support legitimate, relevant business outreach only; maintain suppression/opt-out lists, honor provider rules, and stop follow-ups after opt-out or negative replies. No private-data scraping or controls bypass.
- **Secure by default:** secure identity/session flows, server-side authorization, tenant isolation, encrypted provider credentials, managed secrets, audit logs, and abuse/rate-limit controls.
- **Payment integrity:** paid access is granted only from server-verified subscription state and entitlements. Browser redirects or client-supplied plan values never prove payment. Raw card data is not stored by this application.
- **Evidence over invention:** clearly distinguish verified site facts from inferred suggestions; keep sources and timestamps for research claims.
- **Provider portability:** use interfaces for LLMs, search providers, email, official WhatsApp Business Platform, payment/billing providers, and job queues.
- **Accessible and usable by design:** target WCAG 2.2 Level AA, with keyboard and screen-reader support across core workflows.
- **Fast and technically discoverable:** public pages must meet technical SEO requirements and target good Core Web Vitals; private dashboard/account/billing pages must not be indexed.

## Core product priorities (must-have)

These are the product's primary value, not optional add-ons. Build and test them before expanding into secondary marketing channels:

1. **Business/client discovery and qualification:** understand the client's actual business, offer, audience, market, location, language, ideal customers, and competitors; discover relevant prospects with source evidence, deduplication, fit reasons, and prioritization.
2. **Business-specific outreach:** generate genuinely personalized messages from verified prospect and client facts, with email as a core channel and WhatsApp through the official WhatsApp Business Platform only where eligible. Include review/approval, reply handling, opt-outs, suppression, sending limits, deliverability controls, and auditable outcomes.
3. **Competitor intelligence and search strategy:** identify relevant competing pages and search intent; compare visible content coverage, site structure, technical signals, public authority/link evidence where available, and user experience. Prioritize actions from evidence rather than pretending to know private ranking algorithms.
4. **Website crawlability and SEO improvement:** safely crawl authorized public pages, find indexability and technical/content gaps, create prioritized recommendations, and verify approved changes with repeatable checks. Connect authorized Search Console/analytics data when available to measure real results.

Other channels—paid ads, social publishing, video campaigns, influencer programs beyond core outreach, local/e-commerce specialist modules, reputation monitoring, advanced CRO experiments, and retention automation—are optional modules selected only when relevant to the client's business and approved budget.

## Planned capabilities

1. Public marketing site, product/pricing information, FAQs, policies, and support entry points.
2. Customer registration, verification, secure login, password reset, session management, account export/deletion, and workspace onboarding.
3. Multi-tenant workspaces, team invitations, roles, projects, and server-side authorization.
4. Website and optional authorized GitHub repository analysis; evidence-backed product profile, benefits, audience, pricing, and campaign angles.
5. Public-web prospect discovery for creators, bloggers, newsletters, communities, agencies, partners, and likely customers.
6. Lead qualification, source evidence, fit scoring, deduplication, and CRM stages.
7. Multiple connected email identities and eligible WhatsApp Business accounts, scoped to workspaces/projects/campaigns.
8. Personalized message drafts, human approval queue, scheduling, provider-safe sending limits, reply sync/classification, opt-out handling, and human handoff.
9. Subscription plans, hosted checkout, billing lifecycle, plan entitlements, usage quotas, billing history/receipts where supported, cancellation and failed-payment handling.
10. Analytics for verifiable sends, delivery, replies, clicks, signups, sales, campaign comparison, and ROI where data is available.
11. Audit logs, privacy/retention controls, monitoring, test coverage, backups, and deployment/incident documentation.


12. AI discoverability and responsible self-marketing for this SaaS itself: crawlable public product/docs pages, sitemap, robots.txt, maintained /llms.txt, truthful structured data, evidence-based content planning, and compliant promotion.
13. Core per-client growth engine: competitor-aware SEO and crawlability improvement tied to measurable search outcomes, plus client/business discovery and personalized email/official WhatsApp outreach. Other marketing channels remain optional.

## AI crawler discoverability and self-marketing

The public website should be understandable to both traditional search engines and AI-powered search/research crawlers. The product will expose useful public HTML, a valid sitemap and robots.txt, and a maintained /llms.txt directory, while keeping customer workspaces, reports, leads, billing data and APIs protected. An optional self-marketing workspace will plan and draft useful, source-backed content, run SEO/accessibility checks, require human approval by default, and measure results. No system can guarantee that AI crawlers will visit, index, cite, or recommend the site. Marketing must not use spam, fabricated claims, doorway pages, fake backlinks, or unauthorized platform automation.

See [AI discoverability and self-marketing requirements](docs/AI_DISCOVERABILITY_AND_MARKETING.md) for our own site, and [Client Website Growth Engine](docs/CLIENT_WEBSITE_GROWTH_ENGINE.md) for per-client audits, strategy selection, authorization, execution controls, reporting, and acceptance tests. These are requirements, not claims that every module is already implemented.

## Initial technical direction

- Backend: Python + FastAPI.
- Data: PostgreSQL; migrations required for every schema change.
- Frontend: responsive web application; select and document the implementation stack before substantial UI work.
- Background work: durable job queue and scheduler; do not rely on in-process background tasks for critical sending, AI work, or billing reconciliation.
- Integrations: OAuth/provider adapters; official WhatsApp Business Platform/Cloud API only.
- Billing: provider-agnostic adapter, with the actual provider selected only after verifying merchant eligibility, jurisdiction, supported currencies and operational requirements.
- AI: provider-agnostic LLM interface, structured outputs, validation, evidence checks, and safe fallbacks.
- Deployment: document free-tier quotas, paid limits, production costs, and scaling constraints. Never commit credentials.

## Quality and release gates

- [WCAG, accessibility, SEO, responsive design, and performance standards](docs/QUALITY_STANDARDS.md) are required acceptance criteria, not claims of current compliance.
- [Commercial SaaS requirements](docs/SAAS_PLATFORM_REQUIREMENTS.md) define identity, tenant isolation, subscriptions, entitlements, quotas, billing security, privacy, and required pre-launch tests.
- Target WCAG 2.2 AA and manually test core flows with keyboard and screen reader in addition to automated checks.
- Target good Core Web Vitals at the 75th percentile: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1. Use repeatable Lighthouse runs as lab evidence, not as a substitute for field data.
- Index only intended public pages; keep authenticated and private user data inaccessible to crawlers.
- Security and compliance requirements in [docs/SAFETY_AND_COMPLIANCE.md](docs/SAFETY_AND_COMPLIANCE.md) remain mandatory and take priority over visual, SEO, performance, and revenue goals.
- Do not accept real payments until provider eligibility, verified billing lifecycle, authorization, sandbox tests, policies, support and operational readiness have been checked.
- Do not claim a standard, integration, or end-to-end workflow is complete until relevant checks have run and evidence is recorded.

## Ranking and competitive-performance objective

The product should be engineered to maximize the chance of beating relevant competitors through evidence-led diagnosis, prioritization, approved implementation, and repeated measurement—not merely produce audit reports. Use verified public search guidance and authorized first-party performance data; never claim access to a search engine's private algorithm or promise a fixed ranking result. Establish a baseline per client, define target queries and business KPIs, track changes over a suitable period, and report measured gains, losses, confidence, and likely contributing work. A 90–95% ranking improvement is an ambitious aspiration, not a result that can honestly be guaranteed across every site, query, market, and timeframe.

## Development status

The current repository contains project documentation, a basic FastAPI API, and an initial server-rendered public marketing surface with product/pricing/FAQ pages, robots.txt, llms.txt, and configurable sitemap generation. It is **not yet a complete SaaS product**: customer identity, authenticated dashboard, persistence, tenant authorization, billing, subscription entitlements, provider integrations, and complete workflows still need implementation and verification. The public pages and discovery endpoints also require CI results and deployment configuration checks before being treated as production-ready. No production billing or WCAG/SEO/performance compliance is claimed.

See [docs/ROADMAP.md](docs/ROADMAP.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/SAFETY_AND_COMPLIANCE.md](docs/SAFETY_AND_COMPLIANCE.md), [docs/QUALITY_STANDARDS.md](docs/QUALITY_STANDARDS.md), and [docs/SAAS_PLATFORM_REQUIREMENTS.md](docs/SAAS_PLATFORM_REQUIREMENTS.md).
