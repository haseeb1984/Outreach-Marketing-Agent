# Paddle checkout and customer portal

The existing router is `app/api/paddle_routes.py`; keep it as the single source of truth for Paddle routes.

- `GET /api/v1/billing/paddle/plans`: returns safe plan display metadata and internal plan slugs.
- `POST /api/v1/billing/paddle/checkout`: accepts `workspace_id` and `plan_id` (the internal slug), checks workspace owner/admin access and CSRF, then creates a hosted Paddle transaction using the server-configured `price_id`.
- `POST /api/v1/billing/paddle/portal?workspace_id=...`: opens a portal session for the Paddle customer already mapped to that authorized workspace.

## Configuration

`PADDLE_PLANS_JSON` is keyed by internal plan slug, for example `starter_monthly`. Each value must include `price_id` (a real Paddle `pri_...` ID) and server-side entitlements. Never accept price IDs or entitlements as authoritative from the browser.

- `PADDLE_ENVIRONMENT=sandbox` is the safe default.
- `PADDLE_LIVE_CHECKOUT_ENABLED=false` blocks live checkout until explicitly approved.
- `PADDLE_API_KEY` and `PADDLE_WEBHOOK_SECRET` must be stored in encrypted hosting secrets.

Checkout and portal URLs are restricted to Paddle-controlled HTTPS hosts. Provider failures are sanitized. Portal access requires an existing Paddle customer ID persisted by a verified subscription event.

## Remaining release gates

This code does not prove a real checkout or portal session works. Configure actual sandbox credentials and price IDs; test checkout, signed webhook delivery, duplicate/stale event handling, cancellation, past-due entitlements, and portal management. Production payments remain disabled until the merchant account and launch policies are approved.
