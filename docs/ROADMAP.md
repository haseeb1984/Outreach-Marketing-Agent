# Delivery and conversation roadmap

Percentages represent verified implementation scope, not launch readiness. A phase is complete only after its acceptance checks pass. See [Implementation status and release blockers](IMPLEMENTATION_STATUS.md) for the current evidence-based matrix.

## Current implementation update — 2026-11-26

- Prospect research provider resilience: Brave remains preferred, but a valid empty Brave result set now triggers the configured SerpAPI fallback. If fallback is unavailable, a genuine empty Brave response is preserved as a successful empty result rather than misreported as provider outage. Source-only; no provider credentials or live searches were exercised.
- WhatsApp dispatch gate consistency: the scheduler endpoint, queue API diagnostics and workspace integration-status response now all use the same `dispatch_is_enabled()` helper, which requires both the parsed application setting and exact `WHATSAPP_DISPATCH_ENABLED=true` environment opt-in. This avoids reporting dispatch enabled when the worker's second gate would reject it. Source-only; no tests or live sends.
- WhatsApp outbound queue pagination: the authenticated queue endpoint now returns `has_more` and `next_offset` using one-row lookahead, and the dashboard can incrementally load additional workspace records without duplicates. Queue cancellation remains limited to queued items and releases the associated reserved quota. Source-only; no tests/build/browser acceptance were run.
- The dashboard now lists the latest 50 workspace WhatsApp outbound queue records with account/prospect, status, attempts and timestamps. Workspace owners/admins can cancel a still-queued item; cancellation releases its unused quota reservation. The UI clearly distinguishes queued intent from confirmed delivery. This is source-only and has not been browser-tested.
- WhatsApp outbound implementation clarification: the signed Meta GET verification handshake and raw-body HMAC inbound webhook, durable tenant-mapped event inbox, consent/template/customer-window policy, idempotent quota-backed outbound queue, one-attempt Meta sender, lease-based dispatcher/worker, uncertain-outcome handling, quota settlement, follow-up pause/advance behavior and systemd service are present in source. The dispatcher remains disabled by default and requires both the application setting and exact environment opt-in. The queue API now reports this actual combined gate. This corrects older roadmap wording that described the dispatcher/sender as not implemented; the remaining blocker is Meta sandbox/account acceptance, migration and delivery-status reconciliation operations, and explicit rollout approval—not absence of a worker implementation. No live WhatsApp send has been made.
- Billing dashboard completion (source only): the workspace now loads `/api/v1/billing/account` alongside entitlement decisions, displays the server-verified plan/status/period, current-period consumed/reserved/released usage and recent transaction history, and checks all five quota features. Checkout is limited to configured purchasable plans; the customer portal is shown for an existing Paddle subscription. Workspace admins and owners are supported consistently with the backend authorization policy. Currency amounts are not guessed from a universal two-decimal assumption. No tests, build, sandbox transaction, live payment, deployment or Hostinger package were run for this change.
- Current application implementation source on `main`: `ce5bbc4125f34eef6fb8720356825b0e2cfef963` (billing dashboard, WhatsApp queue management and unified dispatch gating, plus prospect-research fallback to SerpAPI when Brave returns a valid empty result set). This is a source-control reference, not a CI or deployment claim.
- Successful prospect and creator research runs are now persisted as workspace-scoped evidence snapshots with query, provider, parameters, result set and timestamp. Members can list recent runs, restore the exact historical result set, and delete individual runs. Reads and deletes enforce workspace membership and tenant-scoped IDs; workspace deletion cascades history. Account data export includes saved runs. This is not CRM auto-import and restored source links still require fresh human verification.
- Public prospect and creator discovery now share a normalized provider adapter: Brave Search is preferred when configured; SerpAPI is used when Brave is absent or its request/response fails. Both result shapes are normalized before existing URL validation, relevance ranking, deduplication, and human-review gates. The response identifies the provider actually used. `SERPAPI_API_KEY` is optional and server-only; no key is required when Brave remains available. This adds provider resilience, not guaranteed coverage or verified account connectivity.
- The backend readiness check now requires the research-history table, preventing an apparently ready API when migration 069 is missing.
- Added a workspace-aware onboarding checklist to the dashboard, driven by persisted project, CRM, campaign, SMTP-account and draft state. Each step links to its corresponding workflow and clearly preserves the manual-approval/no-automatic-send boundary.
- Campaign management now supports workspace-scoped server-side search across campaign name, client, offer and target audience; status filtering (current, draft, active, paused, archived or all); total counts; and 50-record pagination. Archived campaigns remain excluded from the default current view but can be explicitly found and reviewed.
- The unified reply inbox supports workspace-scoped pagination in 50-thread batches and server-side search across all matching threads by prospect name, company, latest message and channel. Search results paginate independently, so conversations beyond the initially loaded 50 remain discoverable.
- Added a persistent editorial pipeline from website-growth recommendations to workspace content briefs, editorial review, AI-generated SEO article drafts, editable metadata/body, and article approval.
- Added project-workflow dashboard loading so saved briefs survive refreshes and workspace switches.
- Added project-scoped WordPress Application Password storage (with a workspace-default fallback) encrypted with AES-GCM, HTTPS/public-DNS checks, connection verification, and permission checks for authoring/publishing.
- Approved articles can be transferred to WordPress as drafts. Draft retries recover/update the same post; article revisions can be resubmitted and synchronized to an existing WordPress draft.
- Public publishing is a separate admin-only action with explicit browser confirmation and server-side confirmation. No automatic CMS publishing occurs.
- WordPress disconnection revokes the stored encrypted credential while preserving the connection record and linked post history.
- Added the missing CORS PUT allowance required by the dashboard's WordPress connection-save endpoint. Editing an article that already has a WordPress draft now marks the CMS copy out-of-sync and blocks publishing until the updated article is resynchronized.
- Completed customer self-service account privacy controls in the dashboard: download a bounded JSON export (including saved editorial articles and non-secret WordPress connection metadata) and request irreversible account deletion with explicit confirmation, session revocation, identity pseudonymization, and shared-workspace ownership safeguards.
- Added migrations `065`–`068`, backend routes/services, dashboard controls and WordPress operations documentation.
- WordPress connections can now be scoped to individual client projects, with an optional workspace-default fallback. New article transfers prefer the project connection; an existing but unverified project connection blocks delivery rather than silently falling back. The saved CMS connection ID pins retries and publishing to the original site. Existing workspace connections remain intact as the fallback.
- WordPress provider requests now resolve and validate all public A/AAAA records, then connect to a validated IP literal while preserving the original Host header and TLS SNI. This removes the DNS-rebinding gap between validation and the HTTP connection.
- WordPress draft delivery now locks the selected connection and pins the article in the same database transaction. Public publishing also locks its pinned connection while claiming the publish operation, serializing concurrent disconnect and credential changes against both delivery paths. A concurrent site/credential update cannot switch the destination between connection selection and the first delivery attempt; site URL changes are blocked after any article is pinned, including ambiguous attempts without a saved post ID.
- Project settings now display the inherited workspace-default connection as read-only when no project-specific connection exists; project scope cannot accidentally disconnect the workspace fallback. Article delivery buttons no longer depend on whichever connection scope happens to be selected in settings: the backend resolves the correct connection from each saved article's project and enforces fail-closed behavior. Concurrent connection setup for the same scope is serialized. An unpinned project-specific override can be removed to restore workspace fallback; if articles are already pinned to it, disconnect retains a disabled record and keeps delivery fail-closed.
- **Not yet verified:** the latest editorial/CMS and multi-provider research changes have not been built or tested, migrations have not been confirmed applied to a live database, WordPress/SerpAPI staging credentials/provider acceptance have not been exercised, and no Hostinger frontend ZIP/upload or production deployment has occurred.
- Earlier CI and deployment records below apply only to the commits they explicitly identify; they do not validate this newer implementation.

## Earlier verified baseline — 2026-11-24

- Historical application CI baseline: `dd9a499baaf8989cbf4d11531f6882d54ba1cd16`.
- Backend CI passed on this exact SHA: [run 45295962702](https://github.com/haseeb1984/Outreach-Marketing-Agent/actions/runs/45295962702).
- Hostinger Frontend CI passed on this exact SHA: [run 45295962678](https://github.com/haseeb1984/Outreach-Marketing-Agent/actions/runs/45295962678), including type-check, production build, smoke tests, Playwright browser acceptance and Hostinger source-ZIP packaging.
- Vercel production deployment record is READY on this exact SHA. It is the FastAPI backend deployment and does not establish that the separately hosted Hostinger frontend has been uploaded.
- Dashboard controls and endpoint wiring include projects, workspace settings/members, invitations, account export, domain verification, read-only website audits, prospect research review, analytics, integration status, SMTP connection test and delivery-provider event history. The dashboard's current static route test checks rendered UI and wiring; each workflow still needs authenticated database/provider acceptance.
- Account export/deletion and workspace ownership-transfer APIs exist in source; lifecycle and authorization acceptance remain required.
- Project API has an optional disposable-PostgreSQL lifecycle test for create/list/update/archive and cross-workspace denial. It runs only when `OMA_TEST_DATABASE_URL` is configured; do not infer that it ran from the general CI success badge.
- **Billing:** Paddle checkout, customer portal and webhook/lifecycle foundations exist; sandbox checkout, portal, signed webhook delivery, subscription reconciliation and entitlements acceptance remain pending.
- **WhatsApp:** Meta inbound webhook/account/conversation, consent and outbound-queue policy foundations exist; the outbound dispatcher and live sending remain unaccepted and disabled.
- **Email:** durable outbound queue and SMTP adapter foundations exist; staging SMTP inbox delivery and deliverability monitoring remain unverified.
- **Current release gates:** live authenticated customer journey; database-backed lifecycle and tenant-isolation acceptance; SMTP staging delivery; Paddle sandbox lifecycle; Meta staging acceptance and outbound dispatcher; backup restore drill; accessibility/performance; and monitoring/incident readiness.


> The older phase descriptions below are historical snapshots. Where they say billing or WhatsApp has not been implemented at all, use the dated status above: foundations have since been added, but external acceptance and release readiness remain pending.

Percentages represent verified implementation scope, not launch readiness. A phase is complete only after its acceptance checks pass. See [Implementation status and release blockers](IMPLEMENTATION_STATUS.md) for the current evidence-based matrix.

## Implemented foundations (automated tests pass; external operation still needs staging verification)

- Authentication/session and CSRF foundations, workspace roles, rate-limiting foundations, and PostgreSQL-backed identity.
- Workspace-scoped prospect/CRM operations, campaign records, evidence-aware draft generation, explicit human review, and contact controls.
- Durable outbound delivery queue with workspace isolation, per-draft uniqueness, idempotency keys, explicit admin send actions, and send-time approval/suppression checks.
- TLS-only SMTP adapter and safe integration-status diagnostics. Configuration presence is not proof that provider authentication or inbox delivery works.
- Provider-neutral signed inbound-reply webhook with bounded payloads, validation, event deduplication, persistence, and conversation history.
- Read-only website discovery/audit/growth-report services with domain-authorization and SSRF/egress guardrails.
- Responsive same-origin `/app` dashboard wired to authenticated APIs: registration/sign-in, active workspace selection, prospect and campaign creation/listing, draft review, and read-only delivery activity. UI actions respect workspace roles; automated route tests and JavaScript syntax validation pass.
- Public marketing HTML routes, canonical/robots/sitemap helpers, readiness checks, and AI-discoverability requirements.

## Deferred: WhatsApp Business Platform

WhatsApp is intentionally **PENDING** while Meta account setup and same-number Coexistence eligibility are unresolved. Do not delete or deregister the existing WhatsApp Business App number. No live WhatsApp sends are enabled.

Still required before connecting Meta: eligible Coexistence onboarding, provider-specific GET verification handshake, raw-body `X-Hub-Signature-256` validation, native payload normalization, workspace/phone asset mapping, durable inbound/status event persistence, idempotency, official outbound adapter, opt-in/template checks, and staging acceptance. Configuration-status output is diagnostic only.

- Creator discovery results now have a direct **Prepare creator CRM record for review** handoff. It pre-fills the profile URL as both the creator's website and source evidence, preserves the platform and search description as review context, and leaves company details for the user to verify; saving remains an explicit manual CRM action.

## Remaining product and launch work

- **Dashboard extensions:** workspace/project settings, invitations, account export/deletion UI, connected-provider management, and a full browser-based onboarding journey remain incomplete. The current dashboard is a functional core foundation, not a claim that the entire SaaS is launch-ready.
- **Subscriptions and paid entitlements:** billing provider selection, hosted checkout, signed/idempotent billing webhooks, server-side entitlements, atomic quotas, subscription lifecycle, and reconciliation remain incomplete.
- **Research integrations:** live search/provider adapters, provider account connections, evidence capture at scale, and production analytics require implementation and staging verification.
- **Email release verification:** actual encrypted staging SMTP configuration, provider-authenticated smoke test, deliverability evidence, and operational alerts have not been verified from this repository review.
- **Pre-launch production gates:** security review, tenant-isolation review across all resources, accessibility/manual screen-reader checks, performance measurements, incident runbook, and legal/policy launch review remain release gates. **Post-deployment operations:** the owner configures Neon managed backup/PITR retention and snapshot policy after go-live, selects retention based on the live service's recovery objectives and Neon plan, and verifies restore readiness; track this separately from migration acceptance.
- **Analytics:** report only provider-verified sends, delivery, replies, clicks, conversions, and ROI where data exists; do not infer successful external events from local state alone.

## Release rules

1. Work on `main` only; no extra branches.
2. Keep real credentials in encrypted environment/secret storage; never commit or log them.
3. Keep external sending, real payments, and website writes gated until staging acceptance and explicit release approval.
4. CI success verifies only the tested commit and checks; it does not prove production readiness or external provider operation.
