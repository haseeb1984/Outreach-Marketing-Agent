# Paddle subscription webhook setup

The API accepts signed Paddle subscription lifecycle events at `POST /api/v1/billing/paddle/webhook`. This is not a checkout implementation; checkout creation and portal management must be completed and tested separately.

## Required environment

- `PADDLE_WEBHOOK_SECRET`: the secret for the exact Paddle webhook destination.
- `PADDLE_PLANS_JSON`: server-controlled JSON mapping each Paddle price ID to an internal plan slug and entitlement snapshot. Example (replace with real IDs and limits):

```json
{
  "pri_replace_with_real_price_id": {
    "slug": "starter",
    "entitlements": {
      "website_audits": {"enabled": true, "monthly_limit": 10},
      "email_outreach": {"enabled": true, "monthly_limit": 100}
    }
  }
}
```

Configure both values as encrypted deployment secrets. Do not place credentials or real price IDs in source control.

## Security and event handling

- Verify the `Paddle-Signature` header against the raw request body, including its timestamp and HMAC-SHA256 digest; reject stale/replayed timestamps.
- Map the workspace only from signed `data.custom_data.workspace_id`.
- Resolve entitlements from `PADDLE_PLANS_JSON`; ignore any entitlement or plan claims inside custom data.
- Deduplicate events and reject stale subscription snapshots through the existing lifecycle store.
- Only one configured price/plan per subscription is supported. Unknown/mixed prices fail closed.
- Keep the webhook destination configured for subscription lifecycle events. Verify sandbox events and idempotent replay before enabling live billing.

## Remaining release gates

This webhook does not create checkout transactions, customer portal links, or handle refunds/chargebacks. Verify price IDs, workspace metadata propagation, webhook delivery, subscription lifecycle, migrations, and entitlement enforcement in Paddle sandbox before accepting real payments.
