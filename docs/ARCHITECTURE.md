# Architecture

## Product model
This is a commercial multi-tenant SaaS platform, not a single-user utility. Customers register, create a workspace, invite authorized teammates, connect their own provider accounts, choose a subscription, and use only the features and quotas granted by server-verified entitlements. Payment status, plan entitlements, tenant isolation, security, and auditability are core architecture requirements.

## Components
1. Public marketing site for product information, pricing, FAQs, policies, and account entry points.
2. Responsive authenticated dashboard for onboarding, workspaces/projects, product profiles, prospect review, CRM, campaigns, draft approvals, connected accounts, usage, billing, and analytics.
3. FastAPI backend for authentication, authorization, validation, tenant-aware business rules, billing adapter, entitlements, and provider adapters.
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

## Quality gates
- Follow docs/QUALITY_STANDARDS.md for WCAG 2.2 AA, technical SEO, responsive design, and Core Web Vitals.
- Follow docs/SAAS_PLATFORM_REQUIREMENTS.md for customer accounts, subscription billing, entitlements, quotas, tenant isolation, payment security, and launch tests.
- Follow docs/SAFETY_AND_COMPLIANCE.md for outreach safety, privacy, and SSRF.
- A mock is not a production integration. Do not accept real payments until sandbox tests, security checks, merchant eligibility, policies, support and reconciliation are verified.
