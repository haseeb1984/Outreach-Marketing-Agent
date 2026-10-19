# Outreach Marketing Agent

A commercial, multi-tenant SaaS platform for AI-assisted influencer, partnership, and outreach work. Customers will be able to register, manage isolated workspaces/projects, research relevant public-facing prospects, draft personalized outreach, manage replies, review campaign outcomes, and pay for plan-based access.

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

## Development status

The current repository contains project documentation and a basic FastAPI health endpoint. It is **not yet a complete SaaS product**: frontend, identity, persistence, tenant authorization, billing, subscription entitlements, provider integrations, and complete workflows still need implementation and verification in small, testable phases. No production billing or accessibility/SEO/performance compliance is claimed.

See [docs/ROADMAP.md](docs/ROADMAP.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/SAFETY_AND_COMPLIANCE.md](docs/SAFETY_AND_COMPLIANCE.md), [docs/QUALITY_STANDARDS.md](docs/QUALITY_STANDARDS.md), and [docs/SAAS_PLATFORM_REQUIREMENTS.md](docs/SAAS_PLATFORM_REQUIREMENTS.md).
