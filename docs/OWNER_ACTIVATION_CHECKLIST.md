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
| `PLATFORM_ADMIN_EMAILS` | Set to `outreach@juncsys.com` (or a comma-separated list of exact authorized addresses). This remains an environment variable, not a hard-coded identity; configure it in Vercel Production and Preview as appropriate. |
| `AI_API_KEY` | Provider API key for the configured AI base URL/model, if AI drafting is part of launch. |
| `BRAVE_SEARCH_API_KEY` | Search provider API key for prospect/influencer discovery. |
| `TRUSTED_EGRESS_PROXY_URL` | Sensitive Vercel variable. Provision an operator-managed HTTP(S) egress proxy that blocks private, loopback, link-local and cloud-metadata destinations at connection time; do not use an arbitrary public proxy. Set its endpoint in Production and the required Preview/Development environments, redeploy the backend, then verify a controlled public fetch succeeds and private/metadata destinations are blocked. |
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

**Execution update (2026-11-22):** GitHub Actions migration run `45051010880` completed successfully on `main` commit `583117609d7c69a0148104862c546d9b9294ae86`. Its job log explicitly reports migrations 057–062 applied using the GitHub Actions `DATABASE_URL` secret. Backend CI run `45050136091` passed the Python 3.11, 3.12 and 3.13 jobs on the same commit.

**Verification update (2026-11-22):** The owner ran the supplied read-only production SQL verification and reported that every check returned PASS. This covered the `schema_migrations` ledger and the specified schema checks for migrations 057–062. The raw SQL output was not supplied to this agent, so this is recorded as owner-reported verification.

**Migration acceptance:**
- The production ledger and requested schema checks were reported PASS by the owner. No pre-migration backup was created by the migration workflow; this is recorded as historical context, not a remaining migration acceptance blocker.
- Neon managed backup/PITR setup is a separate owner task for production deployment and post-go-live operations (LG-11), not part of this migration batch.

No application deployment was performed as part of the migration run. This checklist records the completed migration execution; it does not authorize any additional production database or application changes.

### Neon backup and recovery — owner action after production deployment

- Configure managed backup/PITR for the production Neon project as part of deployment/go-live operations. This configuration is the owner's responsibility in the Neon Console; it is not performed by the application deployment or GitHub migration workflow.
- Decide the required history/PITR retention in days only after the service is live, using the selected Neon plan, recovery objectives (acceptable data-loss window and restore-time target), expected usage and budget. Do not hard-code a retention duration during pre-launch engineering.
- Review any scheduled snapshot options available on the selected Neon plan, document the chosen policy, and perform/record a restore-readiness check in a safe target before relying on it.
- Track configuration and restore evidence under LG-11. This post-deployment task does not block the already-applied and owner-verified migrations in LG-01.

## 5. Frontend release

Hostinger frontend release remains separate from the Vercel FastAPI backend. The frontend ZIP/package and deployment steps must be verified against the current implementation head before uploading. Do not assume a Vercel backend deployment publishes the Hostinger frontend.

Owner action only if Hostinger access is not available to the connected deployment tool: provide/confirm the intended Hostinger website target and confirm the production deployment window. Do not send passwords in chat.

## 6. Customer-owned SMTP

Each customer should configure their own workspace SMTP credentials in the customer workspace. Validate connection and send only to an operator-owned test mailbox first. Platform SMTP variables are not a substitute for customer-owned SMTP, and no real prospect list should be used for acceptance.

## 7. Minimum information needed from the owner

Reply with non-secret confirmations only:
1. Configure `PLATFORM_ADMIN_EMAILS=outreach@juncsys.com` in the required Vercel environments; additional owner addresses can be added as a comma-separated allowlist.
2. Whether launch includes AI drafting, public prospect discovery, central WhatsApp, and Paddle billing (yes/no for each).
3. Whether GitHub Actions billing/runner restrictions have been resolved.
4. Whether production database migration and production deployment windows are approved (yes/no; no action is taken until explicit approval).

Secret values must be entered directly into Vercel/Meta/Paddle/Hostinger secret settings, not sent here.
