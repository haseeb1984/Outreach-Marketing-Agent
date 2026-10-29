# Outreach Marketing Agent — Paddle sandbox product setup

This catalog belongs to **Outreach Marketing Agent only**. Do not copy product/price IDs from another Paddle project and do not recreate products whose IDs are already configured. The owner supplied the following Outreach Marketing Agent Sandbox Price IDs; these are already represented in `backend/.env.example`. This is not proof that sandbox checkout/webhook acceptance has passed, and Production remains intentionally disabled.

## Recommended initial pricing (USD, monthly)

These are launch hypotheses to validate with early customers, not existing Paddle prices or market-validated claims.

| Internal plan slug | Customer-facing name | Suggested price | Intended customer | Initial entitlement direction |
|---|---|---:|---|---|
| `starter` | Starter | $29/month | Solo operator or very small business | One workspace; modest monthly research/outreach allowance; core SEO checks; manual approval before sending |
| `growth` | Growth | $79/month | Small team managing several campaigns | Higher research and campaign quotas; multiple projects; growth scheduling where operationally enabled; campaign analytics |
| `agency` | Agency | $199/month | Agency or multi-client operator | Highest initial quotas; multiple client projects/workspaces according to actual tenant model; team collaboration and expanded analytics |

Keep the first launch simple: monthly billing only. Consider annual discounts (e.g. 2 months free) only after monthly checkout, cancellation, failed-payment handling, entitlements, and support processes pass acceptance. Do not promise features or limits that the running application does not enforce. Confirm exact numeric quotas against the current quota enforcement before publishing final pricing.

## Existing Sandbox catalog

| Plan | Price | Owner-supplied Sandbox Price ID | Suggested monthly limits |
|---|---:|---|---|
| Starter | $29/month | `pri_01m61xstp0gy07re6ynykhdcgb` | 250 AI drafts, 1,000 emails, 25 website audits, 100 prospect searches; WhatsApp disabled |
| Growth | $79/month | `pri_01m61y1n4enqgf0qbtbm67tkx2` | 1,000 AI drafts, 5,000 emails, 100 website audits, 500 prospect searches, 1,000 WhatsApp sends |
| Agency | $199/month | `pri_01m61y66jhcs5qf0cf9n20a3xf` | 5,000 AI drafts, 25,000 emails, 500 website audits, 2,000 prospect searches, 10,000 WhatsApp sends |

These are the existing owner-supplied Sandbox IDs. Verify them in the correct Sandbox account; **do not create duplicate products just to repeat setup**. The quota numbers are recommended starting limits in the example config and must be reviewed before launch.

## Sandbox configuration and acceptance

1. Keep `PADDLE_ENVIRONMENT=sandbox` and `PADDLE_LIVE_CHECKOUT_ENABLED=false`.
2. Keep the Sandbox API key and webhook destination secret in the API environment's encrypted settings. Do not print or paste secret values into Git.
3. Confirm the existing sandbox notification destination/webhook for:
   `https://<your-api-origin>/api/v1/billing/paddle/webhook`
   Subscribe to the subscription lifecycle events handled by this application: `subscription.created`, `subscription.updated`, `subscription.activated`, `subscription.canceled`, `subscription.past_due`, `subscription.paused`, and `subscription.resumed`. Copy the endpoint's **destination secret key** as `PADDLE_WEBHOOK_SECRET`. The exact event labels shown by Paddle may vary with dashboard/API version.
7. Create/use a **Sandbox API key** scoped only as broadly as required to create transactions and manage the customer portal. Store it as `PADDLE_API_KEY` in the API deployment's secret manager. Never commit credentials to git, frontend variables, docs, screenshots, or chat.
8. Configure `PADDLE_ENVIRONMENT=sandbox` and keep `PADDLE_LIVE_CHECKOUT_ENABLED=false`. Configure `PADDLE_PLANS_JSON` as described below. Keep Production credentials and IDs separate.
9. Deploy to a non-production environment first, then test a successful sandbox checkout and every supported subscription transition. Confirm the webhook signature is accepted, duplicate events are idempotent, stale events do not regress state, and entitlements change only from verified server-side subscription state.

## Plan catalog environment variable

The API reads a JSON object keyed by the stable internal plan slug. The IDs below are the owner-supplied Sandbox IDs already recorded in `backend/.env.example`; use them in the Sandbox environment only. The configured catalog must include all five quota features, including `prospect_research`.

```json
{
  "starter": {
    "name": "Starter",
    "description": "For solo operators and small businesses",
    "price_id": "pri_01m61xstp0gy07re6ynykhdcgb",
    "display_price": "$29",
    "currency": "USD",
    "billing_interval": "month",
    "entitlements": {
      "ai_draft_generations": {"enabled": true, "monthly_limit": 250},
      "email_sends": {"enabled": true, "monthly_limit": 1000},
      "website_audits": {"enabled": true, "monthly_limit": 25},
      "whatsapp_sends": {"enabled": false, "monthly_limit": 0},
      "prospect_research": {"enabled": true, "monthly_limit": 100}
    }
  },
  "growth": {
    "name": "Growth",
    "description": "For growing teams managing multiple campaigns",
    "price_id": "pri_01m61y1n4enqgf0qbtbm67tkx2",
    "display_price": "$79",
    "currency": "USD",
    "billing_interval": "month",
    "entitlements": {
      "ai_draft_generations": {"enabled": true, "monthly_limit": 1000},
      "email_sends": {"enabled": true, "monthly_limit": 5000},
      "website_audits": {"enabled": true, "monthly_limit": 100},
      "whatsapp_sends": {"enabled": true, "monthly_limit": 1000},
      "prospect_research": {"enabled": true, "monthly_limit": 500}
    }
  },
  "agency": {
    "name": "Agency",
    "description": "For agencies managing multiple client projects",
    "price_id": "pri_01m61y66jhcs5qf0cf9n20a3xf",
    "display_price": "$199",
    "currency": "USD",
    "billing_interval": "month",
    "entitlements": {
      "ai_draft_generations": {"enabled": true, "monthly_limit": 5000},
      "email_sends": {"enabled": true, "monthly_limit": 25000},
      "website_audits": {"enabled": true, "monthly_limit": 500},
      "whatsapp_sends": {"enabled": true, "monthly_limit": 10000},
      "prospect_research": {"enabled": true, "monthly_limit": 2000}
    }
  }
}
```

The quotas above are example policy values that the current route enforcement supports; review them before launch. The plan JSON belongs in environment configuration. If the platform-admin billing catalog table is populated, it takes precedence over the environment fallback and must be updated with the same five entitlement keys, including `prospect_research`.

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
