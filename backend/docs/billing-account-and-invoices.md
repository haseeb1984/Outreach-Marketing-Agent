# Billing account, quotas and transaction history

- Authenticated `GET /api/v1/billing/account?workspace_id=...` returns the verified subscription snapshot, active billing period, entitlement policies, current-period consumed/reserved/released quota counts, and the latest 100 Paddle transaction/invoice records. Workspace viewers may read it.
- Existing `POST /api/v1/billing/paddle/portal` remains admin/owner-only and delegates payment methods, cancellation and invoice documents to Paddle-hosted customer portal; the application never handles card data.
- Signed `transaction.completed` and `transaction.payment_failed` notifications are now handled after raw-body signature verification. Workspace mapping uses signed checkout custom data or the previously verified Paddle subscription ID.
- Transaction events are idempotent, timestamp-ordered, tenant-bound, and store only invoice number, status, currency, total minor units and provider IDs; raw payloads and payment details are not stored.
- Apply migration `051_billing_transactions.sql` via the controlled migration process. Readiness requires migration 051.

## External activation still required
Configure the approved Paddle merchant/product/price catalog and notification destination to send transaction.completed, transaction.payment_failed and subscription lifecycle events; apply migration 051; then execute real sandbox checkout, renewal, failed-payment, cancellation, portal and invoice reconciliation before enabling live billing.
