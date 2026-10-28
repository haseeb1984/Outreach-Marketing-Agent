# Meta WhatsApp sender adapter

`app.services.whatsapp_meta_sender.MetaWhatsAppSender` implements a single-attempt
Cloud API adapter for text and parameter-free approved templates. It validates IDs,
API-version format, recipient length, payload bounds, and template language. It disables
redirects for its own HTTP client, never logs provider responses, and returns only the
provider message ID on a confirmed response.

## Delivery semantics

- Definitive 4xx responses are `MetaSendRejected` with a sanitized error code.
- Timeouts, transport failures, rate-limit responses, 5xx responses, malformed success
  bodies, or success responses without a message ID raise `MetaSendUncertain`.
- The adapter never retries. An uncertain result may mean Meta accepted the message;
  callers must not blindly resend it.
- This adapter does not itself check consent, template approval, subscription quota,
  queue state, or dispatch feature flags. A worker must re-run `WhatsAppSendPolicy`
  immediately before dispatch and remain disabled by default until reviewed.

The parameter-free template payload only supports templates without required variables.
Do not dispatch variable-bearing templates until the application has a reviewed,
validated template-parameter mapping.


## Durable queue lease lifecycle

Migration `038_whatsapp_outbound_queue_leases.sql` adds per-claim lease tokens and expiry
timestamps. `WhatsAppOutboundStore.claim_batch()` claims rows in one PostgreSQL statement
using `FOR UPDATE SKIP LOCKED`, so concurrent workers do not claim the same queued row.
A completion update must present the same lease token and an unexpired lease; stale
workers cannot overwrite another worker's state.

Expired processing leases transition to `uncertain`, never back to `queued`. A process may
have crashed after Meta accepted a message but before recording its message ID, so retrying
could send a duplicate. Such rows require provider-side reconciliation/manual review.
The lease store is groundwork only: it is not wired to a dispatch process, does not send
messages, and outbound dispatch remains disabled.
