# Outreach Marketing Agent

A multi-project AI-assisted influencer, partnership, and outreach workspace. The product is designed to help teams understand their websites, research relevant public-facing prospects, draft genuinely personalized outreach, manage replies, and measure campaign outcomes.

## Product principles

- **Research before outreach:** every lead should include a public source/evidence URL, fit score, and a concise reason for inclusion.
- **Human approval first:** all outreach is drafted for review by default. Any later automation must be explicitly enabled, rate-limited, auditable, and subject to eligibility checks.
- **Respectful, compliant contact:** support legitimate, relevant business outreach only; maintain suppression/opt-out lists, honor provider rules, and stop follow-ups after opt-out or negative replies. No private-data scraping or controls bypass.
- **Secure by default:** encrypt provider credentials at rest, use OAuth where available, keep secrets out of source control, and apply tenant/project isolation.
- **Evidence over invention:** clearly distinguish verified site facts from inferred suggestions; keep sources and timestamps for research claims.
- **Provider portability:** use interfaces for LLMs, search providers, email, WhatsApp Business Platform, and job queues.

## Planned capabilities

1. Website and optional authorized GitHub repository analysis; product profile, benefits, audience, pricing, and campaign angles.
2. Multi-project dashboard with campaign setup and roles/access controls.
3. Public-web prospect discovery for creators, bloggers, newsletters, communities, agencies, partners, and likely customers.
4. Lead qualification, source evidence, fit scoring, deduplication, and CRM stages.
5. Multiple connected email identities and WhatsApp Business accounts, scoped to projects/campaigns.
6. Personalized email and WhatsApp message drafts, approval queue, scheduling, and provider-safe sending limits.
7. Reply synchronization and classification, follow-up recommendations, opt-out handling, and human handoff.
8. Analytics for sends, delivery, replies, clicks, signups, sales, campaign comparison, and ROI where data is available.
9. Audit logs, security controls, retention settings, test coverage, and deployment documentation.

## Initial technical direction

- Backend: Python + FastAPI.
- Data: PostgreSQL; migrations required for every schema change.
- Frontend: responsive web dashboard (implementation choice to be documented before substantial UI work).
- Background work: durable job queue and scheduler; do not rely on in-process background tasks for critical sending.
- Integrations: OAuth/provider adapters; official WhatsApp Business Platform/Cloud API only.
- AI: provider-agnostic LLM interface, structured outputs, validation, and safe fallbacks.
- Deployment: start with low-cost tiers, but document quotas, paid limits, and production requirements. Never commit credentials.

## Development status

This repository was empty at project start. Implementation must be delivered in small, testable phases. Do not claim integrations or end-to-end behavior are complete until tests or provider sandbox checks verify them.

See [docs/ROADMAP.md](docs/ROADMAP.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/SAFETY_AND_COMPLIANCE.md](docs/SAFETY_AND_COMPLIANCE.md).


