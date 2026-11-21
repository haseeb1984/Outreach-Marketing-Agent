# Owner activation checklist

Last reviewed: 2026-11-22

This list separates engineering work from owner/provider actions that cannot safely be inferred or completed from repository access. Never paste secret values into GitHub issues, source files, or chat. Enter secrets directly in the relevant provider's environment-variable manager.

## 1. Restore executable GitHub Actions

The private-repository runs after commit `9ef2d11` returned failed jobs with no steps, before a runner started. This is not a test assertion failure.

Owner action:
- Open repository Settings → Actions → General and confirm Actions are enabled for the repository.
- Open the GitHub account/organization Billing and plans / Actions usage page and resolve any failed-payment, spending-limit, or included-minutes restriction.
- Confirm GitHub-hosted runners are permitted for this private repository.
- Then rerun Backend CI, Hostinger Frontend CI, and Generate and verify frontend lockfile on the implementation branch.

Do not weaken branch protection or treat a queued/runner-allocation failure as a passing test.

## 2. Backend production environment configuration

The Vercel environment-key inventory was inspected without decrypting values. Present keys include database/authentication, SMTP, Paddle sandbox and cron configuration. The following keys were not present in that inventory:

| Variable | Owner input/action |
| --- | --- |
| `PLATFORM_ADMIN_EMAILS` | Exact comma-separated email address(es) authorized as platform owner/admin. Use least privilege. |
| `AI_API_KEY` | Provider API key for the configured AI base URL/model, if AI drafting is part of launch. |
| `BRAVE_SEARCH_API_KEY` | Search provider API key for prospect/influencer discovery. |
| `TRUSTED_EGRESS_PROXY_URL` | Trusted crawler egress proxy URL; provision infrastructure first. |
| `META_WHATSAPP_ACCESS_TOKEN` | Meta system-user access token, if central WhatsApp is in launch scope. |
| `META_WHATSAPP_APP_SECRET` | Meta app secret for webhook signature verification. |
| `META_WHATSAPP_WEBHOOK_VERIFY_TOKEN` | High-entropy webhook verification token configured identically in Meta and Vercel. |
| `META_WHATSAPP_PHONE_NUMBER_ID` | Approved WhatsApp Business phone-number ID. |
| `META_WHATSAPP_WABA_ID` | WhatsApp Business Account ID. |
| `META_GRAPH_API_VERSION` | Supported Graph API version, e.g. a currently supported vXX.X value. |

Do not activate WhatsApp dispatch until Meta app/webhook verification, template approval, consent handling, and a controlled test are accepted. The code's dispatch gate remains fail-closed.

## 3. Paddle billing

Current Vercel key inventory includes `PADDLE_API_KEY`, `PADDLE_WEBHOOK_SECRET`, `PADDLE_PLANS_JSON`, and `PADDLE_ENVIRONMENT`. It reports `PADDLE_ENVIRONMENT=sandbox` and `PADDLE_LIVE_CHECKOUT_ENABLED=false`.

Owner/provider action:
- Confirm the configured API key and webhook secret are valid sandbox credentials.
- Confirm every plan maps to a real Paddle sandbox `pri_...` price ID and approved entitlement/quota JSON.
- Configure the sandbox webhook destination and subscribed lifecycle events.
- Complete a sandbox checkout, signed webhook, subscription state update, cancellation/past-due and customer portal test.
- Only after that, provide production price IDs and production credentials, approve the live catalog/pricing and explicitly authorize live checkout. Keep the live gate off until approved.

Never send Paddle secret values in chat.

## 4. Database release

Migrations 057–062 are in the repository release preflight but are not confirmed applied in production. Before applying:
- Confirm the production database and maintenance window.
- Create and verify a restorable backup.
- Review migration plan and rollback/recovery approach.
- Explicitly approve production migration execution.

No production migration is authorized by this checklist.

## 5. Frontend release

Hostinger frontend release remains separate from the Vercel FastAPI backend. The frontend ZIP/package and deployment steps must be verified against the current implementation head before uploading. Do not assume a Vercel backend deployment publishes the Hostinger frontend.

Owner action only if Hostinger access is not available to the connected deployment tool: provide/confirm the intended Hostinger website target and confirm the production deployment window. Do not send passwords in chat.

## 6. Customer-owned SMTP

Each customer should configure their own workspace SMTP credentials in the customer workspace. Validate connection and send only to an operator-owned test mailbox first. Platform SMTP variables are not a substitute for customer-owned SMTP, and no real prospect list should be used for acceptance.

## 7. Minimum information needed from the owner

Reply with non-secret confirmations only:
1. The exact platform-owner email address to authorize in `PLATFORM_ADMIN_EMAILS`.
2. Whether launch includes AI drafting, public prospect discovery, central WhatsApp, and Paddle billing (yes/no for each).
3. Whether GitHub Actions billing/runner restrictions have been resolved.
4. Whether production database migration and production deployment windows are approved (yes/no; no action is taken until explicit approval).

Secret values must be entered directly into Vercel/Meta/Paddle/Hostinger secret settings, not sent here.
