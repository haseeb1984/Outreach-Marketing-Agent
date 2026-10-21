# Subscription entitlement gate (foundation only)

backend/app/services/entitlements.py contains a pure, provider-neutral, fail-closed decision function for a trusted subscription snapshot. It checks subscription status, timezone-aware billing dates, feature enablement, and a configured monthly quota. Missing or malformed state denies access.

## Critical boundary

This module is not a billing integration and does not:
- create checkout sessions or verify payment-provider webhook signatures;
- persist subscriptions, invoices, refunds, cancellations, or billing-event idempotency;
- reserve quota atomically under concurrent requests;
- authenticate the source of the supplied subscription/usage snapshot;
- automatically protect API routes unless each paid operation calls it using trusted database state.

Never pass plan/entitlement values from a browser as authority. A future billing implementation must load verified subscription state from the database, validate signed provider events, make usage reservation/consumption transactional, reconcile provider state, and add route-level tests proving every paid action fails closed. No provider has been selected here and no payment credentials are required for this foundation.
