# Paddle checkout and customer portal

The API exposes authenticated workspace-owner endpoints:

- `POST /api/v1/billing/paddle/checkout`: create a Paddle transaction from a server-configured price ID and return the provider checkout URL.
- `POST /api/v1/billing/paddle/portal?workspace_id=...`: create a customer portal session for the Paddle customer already associated with the authorized workspace.

Both routes require a valid session and CSRF token. Checkout prices are allow-listed by `PADDLE_PLANS_JSON`; workspace ownership is checked server-side. Checkout metadata carries the workspace ID into the signed subscription webhook. The customer portal never accepts a customer ID from the browser.

## Launch safeguards

- Sandbox is the default environment. Live API requests are blocked unless `PADDLE_LIVE_CHECKOUT_ENABLED=true`.
- Provider API failures are sanitized; the API key is never returned or logged.
- Checkout URLs must be HTTPS and hosted on a Paddle-controlled `paddle.com` or `paddle.io` domain.
- Configure real product/price IDs and run checkout, webhook, replay, cancellation, and customer portal tests in sandbox before enabling live billing.
- This does not replace provider account approval, jurisdiction-specific tax/legal review, or production monitoring.
