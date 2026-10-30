# Email provider feedback, replies and suppression

## Outbound message correlation

Every approved outreach email carries an `X-OMA-Delivery-ID` header containing the persisted delivery UUID. The send path also adds RFC 8058 `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers. The unsubscribe URL contains an HMAC-signed, recipient-specific token; it does not expose a bearer credential or permit changing the workspace, prospect, or address.

Outreach sends fail closed unless `OUTREACH_WEBHOOK_SECRET` is at least 32 bytes and `PUBLIC_BASE_URL` is a valid HTTPS origin. Configure both in the backend secret store. Diagnostic SMTP test messages are not outreach and do not carry unsubscribe headers.

## One-click unsubscribe

Mailbox providers can POST to:

`POST /api/v1/email/unsubscribe?token=<signed-token>`

The endpoint validates the HMAC, resolves the exact workspace/prospect/email tuple, sets email suppression with reason `unsubscribe`, and cancels every queued email delivery for that prospect in that workspace. Repeated requests are safe. The endpoint intentionally does not require a login or CSRF token because the signed URL is the one-click authorization.

## Provider feedback event relay

SMTP itself has no standard bounce, complaint, or delivery webhook. Configure the chosen ESP (for example, SES, SendGrid, Mailgun, or Brevo) to send its signed callbacks to an operator-controlled provider adapter/relay. The relay must verify the vendor's native signature, normalize the event, preserve the `X-OMA-Delivery-ID` header (or equivalent provider metadata), and sign the normalized JSON body using `OUTREACH_WEBHOOK_SECRET`.

Forward the normalized event to:

`POST /api/v1/webhooks/email/events`

Header:

`X-Email-Event-Signature: sha256=<hex HMAC-SHA256 of exact raw request body>`

JSON contract:

```json
{
  "provider": "sendgrid",
  "event_id": "provider-unique-event-id",
  "delivery_id": "00000000-0000-0000-0000-000000000000",
  "event_type": "bounced",
  "recipient": "contact@example.com",
  "occurred_at": "2026-10-31T12:00:00Z"
}
```

Supported normalized event types: `delivered`, `deferred`, `bounced`, `complained`, and `unsubscribed`. Only hard bounces should be normalized to `bounced`; transient failures should be `deferred`. The callback recipient must exactly match the address on the persisted delivery. The API derives tenant and prospect identity from that delivery, not from callback-supplied workspace IDs.

Provider events are stored in an idempotent ledger. Delayed older events cannot roll the visible provider status backward. Hard bounce, spam complaint, and unsubscribe events set permanent email suppression and cancel all still-queued email deliveries for that prospect. Suppression is rechecked by the existing enqueue and send-claim paths. A later delivery event never clears suppression automatically.

## Inbound replies and mailbox synchronization

The existing signed normalized inbound-reply endpoint is:

`POST /api/v1/webhooks/inbound-replies`

It persists provider/event/message IDs, channel, reply body and timestamp, marks the prospect replied, and cancels pending outreach. A provider-specific inbound parse or mailbox-sync adapter must authenticate with the provider, map the original recipient/thread to the workspace prospect, then forward the normalized reply with the shared HMAC signature. Generic SMTP credentials alone cannot read an inbox; IMAP/OAuth mailbox synchronization is provider-specific and is not inferred from SMTP account setup.

## Security and operational notes

- Keep `OUTREACH_WEBHOOK_SECRET` unique per environment, at least 32 random bytes, and in encrypted host settings only.
- Verify the vendor's native webhook signature in the relay before signing the normalized callback. The application HMAC is an authenticated relay contract, not a substitute for vendor signature verification.
- Never trust workspace/prospect identifiers supplied by an unverified provider payload.
- SMTP acceptance is not inbox placement. The dashboard's provider status is only as complete as the configured ESP feedback relay.
- Migration `040_email_provider_feedback.sql` must be applied before the new webhook and unsubscribe persistence paths can be used.
