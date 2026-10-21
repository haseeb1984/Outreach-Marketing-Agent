# Billing lifecycle event persistence

Migration: `014_billing_provider_event_ledger.sql`.

`BillingLifecycleStore` accepts only an internal `VerifiedBillingEvent` value. The future HTTP adapter must verify the provider signature over the exact raw request body, validate the provider event timestamp and schema, and resolve the provider subscription to the correct workspace before calling this store. Never trust a workspace ID from a browser or unsigned payload.

- Provider event IDs are unique per provider; duplicates return `duplicate`.
- Subscription snapshots update only when the provider event timestamp is strictly newer than the stored snapshot; old/out-of-order events return `stale`.
- Provider and subscription identity are pinned to the workspace's existing subscription; conflicts abort the transaction.
- Raw payloads, signature headers, tokens, and payment details are not stored.
- The event ledger and snapshot update share one database transaction. Failed writes roll back together.
- This is not yet a billing provider integration: no checkout, signature verification adapter, customer-to-workspace onboarding, refunds, proration, retry scheduler, or paid-route enforcement is included. Do not expose a public endpoint that constructs this internal event object until those controls and provider integration tests are in place.
