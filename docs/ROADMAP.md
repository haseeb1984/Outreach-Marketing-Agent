# Delivery Roadmap

Percentages are estimates of implemented scope, not launch readiness. A phase is complete only when relevant checks pass.

## Authentication and workspace security
Session/CSRF protection and workspace roles have a foundational implementation; production security review remains.

## CRM, campaigns and human approval
Workspace-scoped prospects, evidence-backed drafts and explicit review actions exist. Research integrations remain incomplete.

## Contact controls
Email suppression and evidence-backed WhatsApp opt-in records exist. Jurisdiction-specific consent and external suppression synchronization remain incomplete.

## Outbound delivery queue
- Durable workspace-scoped queue; unique per draft and per-workspace idempotency key.
- Enqueue requires an approved email draft, saved recipient and no email suppression.
- Explicit admin send re-checks approval and suppression immediately before TLS-only SMTP.
- Queue states are not delivery success. Only persisted sent status is reported as sent.
- WhatsApp sending is disabled until an official Business provider adapter is implemented.
- SMTP cannot guarantee exactly-once delivery if the provider accepts a message but the application crashes before status persistence. Automatic retries are disabled; ambiguous outcomes require human reconciliation.

## Remaining
Subscriptions, paid entitlements, scheduled sending, reply/webhook synchronization, influencer discovery and provider analytics are not complete. Secrets must come from environment configuration, never request payloads or logs.
