# Outbound delivery recovery

## Delivery states

- `queued`: approved draft is eligible for an explicit administrator-triggered send.
- `processing`: the server claimed the queue item and is attempting the SMTP handoff.
- `sent`: the SMTP client returned successfully. This confirms handoff to the configured SMTP server, not inbox placement or a reply.
- `failed`: sending did not begin because provider configuration is missing, or message validation failed before SMTP handoff.
- `uncertain`: SMTP/network failure occurred after the handoff attempt began and acceptance cannot be ruled out. This state is terminal for automated sends to prevent duplicate outreach.
- `cancelled`: reserved for a future explicit cancellation workflow.

## Operator procedure for `uncertain`

1. Do not re-enqueue the draft; each draft can have only one delivery record.
2. Inspect the configured SMTP provider's message/event logs using its own secure console. Do not paste credentials or full recipient data into application logs.
3. If provider evidence confirms acceptance, leave the record as `uncertain` until a future reconciliation workflow records the provider evidence. Do not represent it as inbox-delivered.
4. If provider evidence confirms rejection before acceptance, handle the resend manually under the workspace's contact/suppression controls. The current API intentionally does not offer a blind retry/reset operation.

## Integration boundary

The inbound reply endpoint is provider-neutral and requires an HMAC-SHA256 signature using `OUTREACH_WEBHOOK_SECRET` (32+ bytes). An adapter must verify the actual provider webhook signature independently before forwarding a normalized event to this endpoint. Configure secrets in encrypted host settings only. WhatsApp sending remains disabled until an official Business provider adapter and account-specific consent checks are available.
