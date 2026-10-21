# Delivery and conversation roadmap

Percentages represent implemented scope, not launch readiness. A phase is complete only after its automated checks pass.

## Authentication and workspace security
Session/CSRF protection and workspace roles have foundational implementation; production security review remains.

## CRM, campaigns and human approval
Workspace-scoped prospects, evidence-backed drafts and explicit review actions exist. Research integrations remain incomplete.

## Contact controls
Email suppression and evidence-backed WhatsApp opt-in records exist. Jurisdiction-specific consent and external suppression synchronization remain incomplete.

## Outbound delivery
A durable queue uses workspace isolation, per-draft uniqueness, idempotency keys, explicit admin send actions, and send-time approval/suppression checks. TLS-only SMTP is wired. Provider acceptance and database persistence can become ambiguous after a crash; automatic retries are disabled to reduce duplicate-outreach risk.

## Inbound reply inbox
A provider-neutral signed webhook accepts bounded, validated inbound reply events, deduplicates provider event IDs, persists replies, and moves eligible CRM prospects to replied. Workspace members with viewer access can read conversation history. Configure a unique high-entropy OUTREACH_WEBHOOK_SECRET in encrypted deployment settings and adapt each provider's native webhook signature to this gateway; no provider-native adapter or live external account is configured here.

## Remaining
Subscriptions, paid entitlements, scheduled sending, live provider-specific webhook adapters, outbound provider message-ID capture, influencer discovery and provider analytics are not complete. Secrets must come from environment configuration, never request payloads or logs.
