# Outreach Marketing Agent — Roadmap

> Existing implemented foundations are inventoried in FEATURES.md and must not be described as future work. This roadmap contains only remaining product work and release acceptance.

## Priority 1 — Core customer experience
1. Complete workspace/project settings, invitations and account export/deletion UX.
2. Finish connected-provider management and guided onboarding.
3. Complete the end-to-end customer-facing campaign workflow, including prospect research, evidence review, draft review and delivery activity.
4. Complete live research-provider adapters, scalable evidence capture and provenance-backed competitor/search analytics.

## Priority 2 — External delivery and monetization acceptance
1. Complete encrypted staging SMTP acceptance, inbox-delivery evidence, ESP feedback integration and operational alerts.
2. Complete Meta account/number/webhook acceptance without disrupting the existing WhatsApp Business App number.
3. Keep WhatsApp outbound disabled until the dispatcher enforces account-scoped consent, opt-out, approved templates, 24-hour window, idempotency, entitlement/rate limits and provider reconciliation.
4. Complete Paddle merchant eligibility, sandbox checkout, signed subscription lifecycle, cancellation/failed-payment handling and reconciliation.
5. Keep paid operations fail-closed until transactional entitlement/quota enforcement is covered by concurrency tests.

## Priority 3 — Production readiness
1. Complete tenant-isolation and authorization review across APIs, background workers, exports, CRM and billing.
2. Verify Hostinger frontend, Vercel backend and supervised persistent worker deployment/environment parity.
3. Complete PostgreSQL backup/restore drill, monitoring, incident runbook and rollback procedure.
4. Complete accessibility/manual screen-reader, performance/load, privacy/legal and security acceptance.
5. Add measured reporting for verified sends, delivery, replies, clicks, conversions and SEO outcomes only where trustworthy provider/first-party data exists.

## Release safeguards
- Human approval remains the default for outreach.
- Do not enable live WhatsApp sends or real billing before explicit staging acceptance.
- Do not claim production readiness from CI alone.
- Do not fabricate SEO ranking, AI-crawler adoption, delivery, conversion or ROI metrics.
