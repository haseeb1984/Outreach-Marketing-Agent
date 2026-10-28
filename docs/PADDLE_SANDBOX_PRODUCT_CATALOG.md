# Outreach Marketing Agent — Paddle sandbox product setup

This catalog belongs to **Outreach Marketing Agent only**. Do not copy product/price IDs from another Paddle project. The application is deliberately not launch-ready for paid billing until the product owner creates this catalog in the correct Paddle account/environment, configures its IDs and secrets, and completes sandbox checkout/webhook acceptance.

## Recommended initial pricing (USD, monthly)

These are launch hypotheses to validate with early customers, not existing Paddle prices or market-validated claims.

| Internal plan slug | Customer-facing name | Suggested price | Intended customer | Initial entitlement direction |
|---|---|---:|---|---|
| `starter` | Starter | $29/month | Solo operator or very small business | One workspace; modest monthly research/outreach allowance; core SEO checks; manual approval before sending |
| `growth` | Growth | $79/month | Small team managing several campaigns | Higher research and campaign quotas; multiple projects; growth scheduling where operationally enabled; campaign analytics |
| `agency` | Agency | $199/month | Agency or multi-client operator | Highest initial quotas; multiple client projects/workspaces according to actual tenant model; team collaboration and expanded analytics |

Keep the first launch simple: monthly billing only. Consider annual discounts (e.g. 2 months free) only after monthly checkout, cancellation, failed-payment handling, entitlements, and support processes pass acceptance. Do not promise features or limits that the running application does not enforce. Confirm exact numeric quotas against the current quota enforcement before publishing final pricing.

## Create the catalog in Paddle Sandbox

1. Open the Paddle **Sandbox** environment for the account intended for Outreach Marketing Agent. Verify the environment selector before creating anything.
2. Create a product named **Outreach Marketing Agent — Starter**, with a recurring monthly price of **USD 29**.
3. Create **Outreach Marketing Agent — Growth**, recurring monthly **USD 79**.
4. Create **Outreach Marketing Agent — Agency**, recurring monthly **USD 199**.
5. Copy each newly created sandbox **Price ID** (must begin with `pri_`). Do not use product IDs where price IDs are required. Do not reuse IDs from the other project or from Production.
6. Create a sandbox notification destination/webhook for:
   `https://<your-api-origin>/api/v1/billing/paddle/webhook`
   Subscribe to the subscription lifecycle events handled by this application: `subscription.created`, `subscription.updated`, `subscription.activated`, `subscription.canceled`, `subscription.past_due`, `subscription.paused`, and `subscription.resumed`. Copy the endpoint's **destination secret key** as `PADDLE_WEBHOOK_SECRET`. The exact event labels shown by Paddle may vary with dashboard/API version.
7. Create/use a **Sandbox API key** scoped only as broadly as required to create transactions and manage the customer portal. Store it as `PADDLE_API_KEY` in the API deployment's secret manager. Never commit credentials to git, frontend variables, docs, screenshots, or chat.
8. Configure `PADDLE_ENVIRONMENT=sandbox` and keep `PADDLE_LIVE_CHECKOUT_ENABLED=false`. Configure `PADDLE_PLANS_JSON` as described below. Keep Production credentials and IDs separate.
9. Deploy to a non-production environment first, then test a successful sandbox checkout and every supported subscription transition. Confirm the webhook signature is accepted, duplicate events are idempotent, stale events do not regress state, and entitlements change only from verified server-side subscription state.

## Plan catalog environment variable

The API reads a JSON object keyed by the stable internal plan slug. Populate it with the real sandbox Price IDs you just created; the values below are illustrative placeholders and **must be replaced before checkout can work**.

```json
{
  "starter": {
    "name": "Starter",
    "description": "For solo operators and small businesses",
    "price_id": "pri_REPLACE_WITH_OMA_SANDBOX_STARTER_PRICE_ID",
    "display_price": "$29",
    "currency": "USD",
    "billing_interval": "month",
    "entitlements": {}
  },
  "growth": {
    "name": "Growth",
    "description": "For growing teams managing multiple campaigns",
    "price_id": "pri_REPLACE_WITH_OMA_SANDBOX_GROWTH_PRICE_ID",
    "display_price": "$79",
    "currency": "USD",
    "billing_interval": "month",
    "entitlements": {}
  },
  "agency": {
    "name": "Agency",
    "description": "For agencies managing multiple client projects",
    "price_id": "pri_REPLACE_WITH_OMA_SANDBOX_AGENCY_PRICE_ID",
    "display_price": "$199",
    "currency": "USD",
    "billing_interval": "month",
    "entitlements": {}
  }
}
```

The empty `entitlements` objects above are intentionally not a finished entitlement policy. Populate them only with entitlement keys/limits that the application actually enforces. The plan JSON should be stored as a deployment secret/config value, not added to source control with real IDs. If the platform-admin billing catalog table is populated, it takes precedence over this environment fallback; keep the active catalog consistent and audit which source is in use.

## Acceptance checklist

- [ ] All three products/prices exist in Paddle Sandbox under this project's own catalog.
- [ ] All three Price IDs are sandbox IDs and map one-to-one to `starter`, `growth`, and `agency`.
- [ ] API key and webhook destination secret are configured only in the sandbox API environment.
- [ ] Public plan response shows names/prices but never provider Price IDs, credentials, or internal entitlements.
- [ ] Checkout is restricted to an authenticated workspace admin and uses the configured plan price.
- [ ] A signed webhook is accepted; invalid signature and old timestamp are rejected.
- [ ] Duplicate webhook delivery is idempotent; stale/out-of-order subscription events cannot restore cancelled access.
- [ ] Cancellation, pause, past-due, resume, and activation produce the expected entitlements.
- [ ] Customer portal uses the sandbox portal host.
- [ ] Live checkout remains disabled; no real customer is charged during sandbox testing.

## Important boundaries

- This repository change documents the intended catalog and process; it does **not** create products inside Paddle. Product creation requires access to the correct Paddle dashboard/account or authenticated Paddle API credentials.
- Never put real credentials in GitHub Actions logs or expose their values in diagnostics.
- Before Production, create a separate production catalog and production webhook destination, review the displayed pricing/legal/support details, and explicitly enable live checkout only after a separate production acceptance.
