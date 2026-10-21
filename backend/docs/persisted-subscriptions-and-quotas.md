# Persisted subscription and quota reservation foundation

Migration: `013_subscription_entitlements_and_usage.sql`.

- `workspace_subscriptions` is a server-owned snapshot. Its writer must be a future verified, idempotent billing-provider lifecycle handler; client plan claims must never update it.
- `SubscriptionStore.get_entitlement` reads the snapshot and current-period usage from PostgreSQL and fails closed if the subscription is absent or invalid.
- `reserve_usage` locks the workspace subscription row in a transaction, evaluates the current server snapshot, and reserves a quota unit before billable work. This serializes competing reservations for a workspace and makes a repeated key idempotent.
- Call `finish_reservation(..., outcome="consumed")` after the protected operation succeeds, or `outcome="released"` only when the operation is known not to have occurred. Ambiguous external sends must not be released or retried blindly.
- Use a cryptographically random request idempotency key scoped to workspace and feature. Do not derive it from client-supplied plan data.
- Provider webhook signature verification, provider event deduplication/order handling, checkout, cancellation/refund reconciliation, admin billing UI, and route-level enforcement are not implemented by this foundation. Until those exist, paid features must not be advertised as subscription-enforced or billing-ready.
- Apply this SQL migration through the deployment's controlled migration procedure before instantiating this store. Application startup intentionally does not auto-run schema changes.
