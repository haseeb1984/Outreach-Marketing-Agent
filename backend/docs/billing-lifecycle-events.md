# Paddle Billing lifecycle integration

The application now has a Paddle adapter at `/api/v1/billing/paddle` and retains the provider-neutral lifecycle ledger.

## Environment configuration

- `PADDLE_ENVIRONMENT=sandbox` for Paddle sandbox; use `production` only after sandbox acceptance.
- `PADDLE_API_KEY`: server-side Paddle API key with the minimum permissions needed to create transactions.
- `PADDLE_WEBHOOK_SECRET`: the secret for the specific Paddle notification destination.
- `PADDLE_PLANS_JSON`: server-owned JSON mapping plan slugs to actual Paddle recurring price IDs and entitlements, e.g. `{"starter_monthly":{"price_id":"pri_actual_id","entitlements":{"email_outreach":{"enabled":true,"monthly_limit":100}}}}`. The example limit is illustrative, not an approved product/pricing decision.

Never put these values in source control, browser code, URLs, logs, or user-visible error responses. Configure secrets in the hosting provider's encrypted environment settings.

## Routes

- `POST /api/v1/billing/paddle/checkout`: requires an authenticated session and admin/owner access to the workspace. Request body includes `workspace_id` and a configured `plan_id`; the client cannot supply arbitrary Paddle price IDs or entitlements. Returns a hosted checkout URL only when Paddle provides one.
- `POST /api/v1/billing/paddle/webhook`: verifies `Paddle-Signature` over the exact raw body with HMAC-SHA256 and a bounded timestamp window before processing supported subscription lifecycle events. Configure this exact HTTPS URL as a Paddle notification destination.
- `GET /api/v1/billing/entitlements`: existing authenticated, read-only status endpoint.

Subscribe the notification destination to at least `subscription.created`, `subscription.updated`, `subscription.activated`, `subscription.resumed`, `subscription.paused`, `subscription.past_due`, and `subscription.canceled`. Paddle propagates transaction custom data to the subscription, which is how the signed event is linked to the server-created workspace checkout.

## Safety properties and remaining release gates

- Browser redirects never grant access; only a valid signed subscription event updates the server-owned snapshot.
- The event ledger deduplicates event IDs and ignores older snapshots.
- Unknown plans, missing workspace mapping, unsupported statuses, bad signatures, and unconfigured billing fail closed.
- Raw webhook payloads and secrets are not persisted or logged.
- Canceled/paused Paddle events omit `current_billing_period`; the adapter preserves the previous period where available while the non-active status denies paid access.

This integration is source-implemented, but it is **not production-ready or payment-verified yet**. Before charging customers: create/approve the Paddle product and recurring prices, configure sandbox API key and notification destination secret in hosting, run real sandbox checkout and lifecycle simulations, verify the database migrations/readiness, wire quota enforcement into each paid operation, and only then consider production credentials. No prices or entitlements are assumed by this document.
