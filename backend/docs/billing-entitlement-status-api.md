# Authenticated billing entitlement status endpoint

GET /api/v1/billing/entitlements?workspace_id=...&feature=email_outreach

- Requires an authenticated session and viewer access to the requested workspace.
- Reads only the server-owned subscription snapshot and usage counters through SubscriptionStore.
- Returns the decision reason and remaining quota, without exposing customer/payment identifiers or secrets.
- Missing subscription state, missing quota configuration, expired periods, or unavailable storage fail closed.
- This is a read-only dashboard/status endpoint. It does not reserve quota or automatically enforce a decision on campaign, prospect, or delivery operations.
- Paddle checkout and signed webhook routes now exist at `/api/v1/billing/paddle/checkout` and `/api/v1/billing/paddle/webhook`. They are not production-verified until real Paddle sandbox credentials, plan IDs, notification destination, and end-to-end tests are configured. Never let a browser write subscription state. The status endpoint alone does not automatically enforce entitlements in every paid operation.
