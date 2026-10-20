# Workspace outreach drafts and human review

These endpoints create and review draft copy only. There is deliberately no provider send call, scheduler, or delivery job in this workflow.

All endpoints require an authenticated session cookie. Mutating requests require the configured HTTPS `Origin` and the session-bound `X-CSRF-Token` header. Workspace membership and role are checked server-side on every request.

## Create a draft

`POST /api/v1/workspaces/{workspace_id}/outreach-drafts`

Minimum role: `member`. Rate limited. Example request:

```json
{
  "channel": "email",
  "client_business": "Example Agency",
  "client_offer": "technical SEO audits",
  "prospect_name": "Example Shop",
  "prospect_evidence_url": "https://example.com/about",
  "verified_relevance": "The public site lists two store locations.",
  "verified_facts": ["The public site lists two store locations."],
  "call_to_action": "a short introductory call",
  "whatsapp_opt_in_confirmed": false
}
```

The evidence URL must use HTTPS and must not include user-info, a query string, or a fragment. Facts are bounded and are supplied by the user/research stage; the generator does not independently verify them. The response is a draft requiring review, not a claim that the prospect or supplied facts were independently verified.

For WhatsApp, `whatsapp_opt_in_confirmed` must be `true`. This flag is an operator attestation; the service does not itself verify or store external proof of consent.

## List drafts

`GET /api/v1/workspaces/{workspace_id}/outreach-drafts?limit=50&status=draft_requires_human_review`

Minimum role: `viewer`. Limit is 1–100. The optional status filter is `draft_requires_human_review`, `approved`, or `rejected`.

## Record a human review

`POST /api/v1/workspaces/{workspace_id}/outreach-drafts/{draft_id}/review`

Minimum role: `admin`. Body:

```json
{"decision": "approved", "note": "Reviewed source evidence"}
```

A pending draft can be reviewed once. The decision and actor are recorded in the database and in `security_audit_events`; audit metadata contains only the draft identifier, channel/decision, not the message body. A repeat or unknown draft returns a conflict response. Approval means the reviewer approved the copy for the next product stage only: the API explicitly returns `delivery_status: not_sent`.

## Release boundary

This feature does not send email or WhatsApp, connect provider accounts, validate consent with a provider, schedule follow-ups, or guarantee the accuracy of supplied research facts. Those require separate integrations, policy checks, credential handling, consent evidence, and delivery-specific approval controls.

## Workspace campaigns

Campaign metadata is managed separately from sending:

- `POST /api/v1/workspaces/{workspace_id}/campaigns` creates a campaign (minimum role: `member`; CSRF-protected and rate-limited).
- `GET /api/v1/workspaces/{workspace_id}/campaigns?limit=50&status=draft` lists campaigns (minimum role: `viewer`; limit 1–100).
- Campaign goals: `partnerships`, `influencer_outreach`, `sales`, `brand_awareness`, `other`.
- Channels: `email`, `whatsapp`, `multi_channel`. Status filters: `draft`, `active`, `paused`, `completed`, `archived`.

Campaign website URLs are stored as metadata only; creation does not fetch them. URLs must be clean HTTPS URLs without credentials, query strings, or fragments. A draft may optionally include `campaign_id`; the database enforces that a linked campaign belongs to the same workspace. Deleting a campaign referenced by drafts is constrained rather than silently unlinking history.
