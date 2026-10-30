# SMTP and email operations

## Workspace SMTP account lifecycle

Workspace administrators manage SMTP identities at `/api/v1/integrations/email-accounts`:

- `POST` creates an account in `pending_test`; the password is encrypted with AES-GCM and workspace/account-bound associated data. The API never returns encrypted or plaintext credentials.
- `GET` lists safe account metadata for workspace members.
- `POST /{account_id}/test` checks STARTTLS and SMTP authentication without sending a message. Activation is conditional on the exact account `updated_at` version that was tested, so a concurrent credential rotation cannot be accidentally activated by a stale test.
- `POST /{account_id}/send-test` requires workspace-admin authorization, CSRF validation, and explicit confirmation. It sends one diagnostic message only to that account's configured sender address. SMTP acceptance does not prove inbox placement.
- `PUT /{account_id}` rotates credentials and returns the account to `pending_test`. Queued messages tied to the old identity are atomically retired as failed with `email_account_credentials_rotated`; they are not unexpectedly released after a later retest.
- `DELETE /{account_id}` disables the identity and atomically retires its queued messages with `email_account_disabled`.

Supported accounts require STARTTLS on port 587 and an allow-listed submission host (Gmail, Microsoft, Outlook, Zoho, Brevo, SendGrid, Mailgun, or Amazon SES SMTP endpoints). Unsupported hosts and non-TLS configurations are rejected. The deployment-level SMTP configuration remains a fallback only when a queued delivery does not select a workspace account.

## Sending and recovery behavior

Outreach sending is a separate explicit admin action after a draft is approved and queued. The send claim rechecks campaign state, contact suppression/reply state, recipient email, and selected SMTP account status. Usage is reserved before a send. Provider/network outcomes that may have been accepted remotely are marked `uncertain`, consume the send quota, and are never automatically retried. Stale processing records can be reconciled to the same uncertain state.

Definite pre-send configuration failures are recorded as failed and do not represent a delivered message. Operators should correct the account/configuration and create a newly approved delivery rather than blindly replaying an ambiguous SMTP submission.

## Operational boundaries

SMTP is a message-submission protocol, not a universal delivery-event or mailbox-sync protocol. A successful SMTP submission is not proof of inbox placement, delivery, open, or click. The application now accepts signed normalized provider feedback and inbound-reply callbacks, persists delivery events, and applies bounce/complaint/unsubscribe suppression. See [Email provider feedback, replies and suppression](EMAIL_PROVIDER_FEEDBACK.md) for the relay contract. The selected ESP's native webhook signature and inbound mailbox/parser integration must still be configured at the provider relay; generic SMTP credentials alone cannot read a mailbox.
