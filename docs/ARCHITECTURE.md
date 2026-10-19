# Architecture

## Components
1. Responsive dashboard for project onboarding, product profiles, prospect review, CRM, campaigns, approval queue, connected accounts and analytics.
2. FastAPI backend for authentication, authorization, validation, business rules and provider adapters.
3. PostgreSQL as the durable source of truth for users, projects, prospects, campaigns, messages, account metadata, suppression records and audit events.
4. Durable worker/queue for research and sending jobs, with idempotency, retries, cancellation and per-account/project limits.
5. Provider adapters for website fetch, authorized GitHub reads, search, LLM, email, official WhatsApp Business Platform and analytics events.
6. Security layer for tenant isolation, encrypted secrets, audit events, rate limits, retention and monitoring.

## Data boundaries
- Enforce project membership server-side on every request.
- Encrypt provider tokens at rest; never return them to the browser after connection.
- Store only public-source prospect details needed for legitimate professional contact.
- Check suppression/opt-out immediately before each send and follow-up.

## Initial backend layout
- `backend/app/main.py`: API entry point.
- `backend/app/core/config.py`: environment-backed settings.
- `backend/tests/`: automated tests.
- `docs/`: product, architecture and operational requirements.

## Main workflows

### Product discovery
User submits website and optional authorized repository → validate target/access → fetch only public or authorized material → extract structured facts with evidence → user reviews profile → approved profile grounds campaign drafts.

### Prospect research
Campaign definition → search permitted public sources → normalize/deduplicate candidates → attach evidence URL and observation date → calculate transparent fit score and discovery reason → user reviews candidates → approved prospects enter CRM.

### Outreach
Eligible prospect and product profile → generate draft → check policy, suppression and duplicates → human approval → queued provider send with idempotency key and limits → persist provider result → sync/classify replies → suggest follow-up or human handoff.

### Analytics
Ingest verifiable provider and user-supplied conversion events → reconcile by campaign/prospect → report metrics and attribution assumptions. Never fabricate delivery, clicks, sales or ROI.

## Reliability
- External calls use timeouts, bounded retries and rate limits.
- Queue jobs are idempotent and persist state transitions.
- Secrets and personal data are redacted from logs.
- Schema changes use versioned migrations.
- Sending jobs re-check suppression, eligibility, limits and account health at execution time.
