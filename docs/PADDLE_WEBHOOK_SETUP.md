# Paddle webhook setup

The existing Paddle router accepts signed subscription lifecycle events at `POST /api/v1/billing/paddle/webhook`. It verifies the raw-body `Paddle-Signature` HMAC with a five-minute timestamp window, maps the signed workspace and plan metadata, and persists the event through the idempotent billing lifecycle store.

## Required environment

- `PADDLE_WEBHOOK_SECRET`: the secret for the exact Paddle notification destination.
- `PADDLE_PLANS_JSON`: JSON object keyed by internal plan slug; each entry includes a Paddle `price_id`, display metadata, and server-controlled `entitlements`.

Example shape (replace with real recurring price IDs and reviewed limits):

```json
{
  "starter_monthly": {
    "price_id": "pri_replace_with_real_price_id",
    "name": "Starter",
    "description": "For small teams",
    "display_price": "replace with approved price",
    "currency": "USD",
    "billing_interval": "month",
    "entitlements": {
      "website_audits": {"enabled": true, "monthly_limit": 10},
      "email_sends": {"enabled": true, "monthly_limit": 100}
    }
  }
}
```

## Security and acceptance

- Use encrypted deployment secrets; never commit API keys, webhook secrets or real customer data.
- Checkout metadata carries `workspace_id` and `plan_id`. The signed webhook must map the declared plan to the configured Paddle price ID before updating entitlements.
- Duplicate events are idempotent; stale subscription snapshots must not overwrite newer state.
- Verify valid signatures, invalid signatures, stale timestamps, duplicate deliveries, out-of-order events, trialing, cancellation, past-due state and unknown plan IDs in sandbox.
- Do not enable live billing until merchant eligibility, policies, database migrations, operational alerts and a real sandbox lifecycle are accepted.
