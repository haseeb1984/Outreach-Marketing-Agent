# Commercial SaaS Platform Requirements

This document defines requirements for a multi-user, paid SaaS product. These are implementation requirements, not claims that billing or security features already exist.

## 1. Customer lifecycle
- Public marketing site with clear product scope, feature descriptions, pricing, FAQs, support/contact, privacy policy, terms, acceptable-use policy, and cancellation/refund information appropriate to the launch jurisdiction.
- Account registration, email verification, secure sign-in, sign-out, password reset, session management, and account deletion/export flows.
- Onboarding creates an isolated workspace; users can create projects inside that workspace.
- Workspace owners can invite members and assign least-privilege roles. Team membership and project access must be checked server-side on every operation.
- Provide account, workspace, security, billing, subscription, usage, connected-app, and support settings.

## 2. Billing and subscription entitlements
- Implement a provider-agnostic billing interface; select and document a payment provider that legally supports the merchant's country, currency, customer locations, and intended business model before production integration.
- Keep card details in the payment provider's hosted/approved payment flow; never store raw card numbers or CVV.
- Verify webhook signatures, validate event types, tolerate retries/out-of-order delivery, and process events idempotently.
- Treat the server-side billing record and verified provider events as the source for subscription state. Never grant paid access based only on a browser redirect or client-provided plan name.
- Model plans, entitlements, subscription status, billing period, trial if offered, cancellation-at-period-end, failed payment/past-due state, grace policy, and account access behavior explicitly.
- Use a transactional entitlement check on every paid feature and background job. A plan name in the UI is not authorization.
- Support upgrade/downgrade, cancellation, renewal, invoices/receipts where supported, failed-payment recovery, refunds/chargebacks, and support-assisted reconciliation.
- Do not delete customer data immediately when a subscription expires. Define a disclosed retention/grace/export policy and apply it consistently.
- Never promise recurring billing, tax handling, refunds, or a payment method until the chosen provider and launch configuration have been verified.

## 3. Usage quotas and cost protection
- Define plan-specific limits for projects, seats, prospect research, AI requests/tokens, message drafts, connected accounts, storage, and outreach sends where applicable.
- Reserve/consume quota atomically so concurrent requests cannot overspend limits. Background workers must re-check entitlement, quota, account status, and suppression rules at execution time.
- Separate user-visible usage from internal cost monitoring. Add budget caps, per-provider limits, alerts, and a global emergency kill switch.
- Fail closed for paid actions when entitlement status cannot be safely verified; provide a clear recoverable error rather than silently granting access.

## 4. Tenant isolation and account security
- Use stable workspace/tenant identifiers and enforce ownership/membership at the service and database query layer. Never trust tenant IDs supplied by a browser without authorization checks.
- Add automated cross-tenant tests for every resource family, including projects, prospects, messages, reports, integrations, billing records, and exports.
- Store password hashes with a current, vetted password-hashing implementation; never store plaintext passwords.
- Protect sessions with secure, HttpOnly, appropriate SameSite cookies if cookie sessions are used; implement CSRF protection where applicable, session rotation, expiry, and revocation.
- Rate-limit login, password reset, signup, invitation, expensive AI/search actions, and webhook processing. Avoid revealing whether an email address has an account.
- Offer MFA for privileged accounts before production where feasible; require stronger protection for administrative operations.
- Keep secrets in deployment secret storage, encrypt provider credentials at rest using managed keys where available, support token revocation, and redact secrets from logs.
- Apply least privilege to staff/admin access; audit sensitive support/admin actions and do not permit staff to browse customer content without a defined, audited support workflow.

## 5. Payments and billing security
- Use hosted checkout or provider-approved tokenization. Do not handle card data directly unless the business has deliberately implemented the applicable compliance scope.
- Verify webhook signatures against the raw request body; reject invalid signatures and replayed/non-idempotent events.
- Reconcile subscription state with the provider periodically and expose safe operational alerts for mismatches.
- Prevent customer A from reading, changing, cancelling, or receiving invoices for customer B's subscription.
- Never trust success/cancel URLs, frontend price values, webhook payloads without signature verification, or client-side entitlement flags.

## 6. Privacy and compliance
- Publish accurate privacy, terms, cookie/analytics disclosures where applicable, data retention/deletion and support contact details before accepting customers.
- Collect only necessary data; define retention and deletion for leads, messages, provider tokens, audit logs, backups, and billing records.
- Provide user data export/deletion workflows while preserving records that must legally or operationally be retained; document exceptions clearly.
- Follow applicable data protection, anti-spam, email, WhatsApp, consumer, tax, and payment-provider requirements for the actual launch jurisdictions. Obtain qualified legal/accounting advice where required; this document is not legal advice.
- No scraping private accounts, bypassing provider restrictions, deceptive outreach, fabricated claims, or sending after opt-out/refusal/bounce/complaint.
- Separate marketing consent and product/service communications where required. Honor unsubscribes and suppression checks across campaigns.

## 7. Reliability and operations
- Use a relational database with versioned migrations, backups, restore drills, health/readiness checks, structured redacted logs, metrics, alerts, and an incident runbook.
- Use durable jobs for expensive research, AI tasks, billing reconciliation, email/WhatsApp sync, and sends. Apply idempotency, bounded retries, dead-letter handling, cancellation, and concurrency controls.
- Make destructive or financial actions auditable. Keep a clear audit trail for plan changes, entitlement decisions, webhook processing, admin actions, and message sends.
- Define backup retention, recovery point/time objectives, incident response ownership, vulnerability disclosure/contact process, dependency scanning, and patch cadence before launch.
- Have separate development/staging/production configuration; never use production customer data in tests without a justified, protected process.

## 8. Required tests before accepting real payments
- Authentication, password reset, session expiry/revocation, role checks, and account recovery.
- Cross-tenant isolation and object-level authorization for all customer-owned resources.
- Billing webhook signature, duplicate, retry, out-of-order, cancellation, failed payment, refund, and reconciliation tests using provider sandbox fixtures.
- Entitlement/quota race tests, including concurrent API requests and queued jobs.
- Price tampering, forged redirect, forged webhook, replay, IDOR, CSRF, rate-limit, and secret-leak tests.
- Accessibility, SEO/privacy crawl, responsive browser tests, load/performance checks, backup restore rehearsal, and monitoring/alert verification.
- Production payment launch remains blocked until provider merchant eligibility, live configuration, terms/privacy, support process, and end-to-end sandbox/live smoke checks have been reviewed.

## 9. Release policy
Critical/high authentication bypass, cross-tenant leakage, payment/entitlement bypass, secret exposure, quota race, suppression bypass, or duplicate-send vulnerability blocks release until fixed and retested. No fake billing UI, hardcoded successful payment, mock integration presented as real, or manual database toggle as a substitute for production billing.
