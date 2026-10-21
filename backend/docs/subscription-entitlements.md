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


## Route enforcement added

The authenticated `POST /api/v1/drafts` operation now reserves one `ai_draft_generations` unit from the trusted subscription store before generating a draft. The request must include a bounded `idempotency_key`; the server namespaces it and rejects replayed keys so a retry cannot generate a second draft. Missing subscription service fails closed, quota exhaustion returns 429, and missing/disabled entitlement returns 403. Known pre-generation validation/not-found/duplicate-pending failures release the reservation. Successful generation consumes it. Unexpected persistence errors consume conservatively because the database outcome may be ambiguous.

Configure the trusted subscription snapshot with an explicit `ai_draft_generations` entitlement, for example `{"enabled": true, "monthly_limit": 250}`. Missing entitlement configuration denies generation. This remains quota enforcement only: it does not activate checkout, paid subscriptions, or any payment provider. Provider-specific billing remains blocked until a provider is selected and verified.
