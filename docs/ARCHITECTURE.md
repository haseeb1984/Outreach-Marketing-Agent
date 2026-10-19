# Architecture

## High-level components

1. **Web dashboard** — project onboarding, product profile, prospect review, CRM, campaigns, approval queue, connected accounts and analytics.
2. **FastAPI application** — authenticated API, input validation, authorization, business rules and provider adapters.
3. **PostgreSQL** — durable source of truth for users, projects, prospects, campaigns, messages, integrations metadata, suppression records and audit events.
4. **Worker/queue** — scheduled research and sending jobs with idempotency keys, retries, cancellation and per-account/project limits.
5. **Provider adapters** — website fetcher, authorized GitHub reader, search provider, LLM provider, email provider, WhatsApp Business Platform and analytics/event sources.
6. **Audit/security layer** — tenant isolation, encrypted secrets, structured audit records, rate limits, retention and operational monitoring.

## Data boundaries
- A user can access only projects they own or have been granted access to.
- Project-scoped campaigns, prospects, connected accounts and reports must be authorized server-side on every request.
- Provider access tokens are encrypted at rest and never returned to clients after connection.
- Raw prospect evidence should contain public URLs and the minimum data needed for legitimate professional contact.
- Suppression/opt-out state must be checked immediately before every send, not just when a draft is created.

## Initial backend layout
- `backend/app/main.py`: FastAPI application entry point.
- `backend/app/core/config.py`: environment-backed settings.
- `backend/tests/`: automated tests.
- `docs/`: product and operational requirements.

As the codebase grows, split routers, models, services, and provider adapters into separate modules. Do not introduce a complex service topology before there is a tested need.

## Key workflows

### Product discovery
User submits website URL and optional authorized repository → validate URL and access → fetch only public/authorized material → extract structured facts with evidence → user reviews/edits the product profile → profile becomes the grounding context for campaign drafts.

### Prospect research
Campaign definition → query approved public sources → normalize and deduplicate candidates → attach evidence and discovery reason → calculate transparent fit score → user reviews candidates → approved prospects enter CRM.

### Outreach
Eligible prospect + project product profile → create draft → policy/opt-out/duplicate checks → human approval → provider send job with idempotency key and limits → provider result and message event saved → reply sync/classification → follow-up recommendation or human handoff.

### Analytics
Ingest verifiable provider events and user-supplied conversion events → reconcile by campaign/prospect → report counts and attribution assumptions. Never fabricate delivery, clicks, sales, or ROI when no event source exists.

## Reliability
- External calls have timeouts, bounded retries and rate limits.
- Queue jobs are idempotent and persist state transitions.
- Secrets and personal data are redacted from logs.
- Database changes use versioned migrations.
- Sending jobs re-check consent/eligibility, suppression, limits and account health at execution time.
