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
