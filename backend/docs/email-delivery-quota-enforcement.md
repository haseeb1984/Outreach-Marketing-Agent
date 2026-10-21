# Email delivery quota enforcement

The explicit admin send endpoint now reserves the server-owned `email_sends`
entitlement for the queued delivery before claiming it for SMTP. The reservation
key is derived from the delivery UUID, not from a caller-controlled retry key,
so changing request keys cannot multiply quota.

- Missing/inactive subscriptions and missing feature/quota policy fail closed.
- Exhausted quota returns HTTP 429; other entitlement denials return HTTP 403.
- A delivery that cannot be claimed, or a provider that is definitely not called,
  releases the reservation.
- A successful send consumes the reservation.
- An ambiguous SMTP/network outcome consumes quota and remains `uncertain`; it
  is not automatically retried because the provider may have accepted the email.
- If quota persistence fails after SMTP accepts a message, the endpoint reports a
  persistence error and does not release the reservation.

Plan configuration must include `email_sends`, for example
`{"enabled": true, "monthly_limit": 100}`, in a trusted server-side subscription
snapshot. Browser input never sets this policy.

This is an enforcement foundation for the explicit email send operation, not a
complete billing launch: verified provider webhooks/checkout are not connected,
and no production billing plan should be written manually from a browser.
