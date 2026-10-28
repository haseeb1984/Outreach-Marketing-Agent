# WhatsApp dispatch worker

The worker is implemented at `app.workers.whatsapp_dispatch_worker`. It is deliberately
disabled unless **both** `WHATSAPP_DISPATCH_ENABLED=true` and the parsed application
setting `whatsapp_dispatch_enabled=true` are present. Both derive from the same
environment variable when set before process startup; the second gate is intentionally
retained so tests/operators can independently force the worker off. The default is off.

## Before enabling in a non-production environment

1. Apply migrations through `038_whatsapp_outbound_queue_leases.sql`.
2. Configure a valid 32-byte base64 credential encryption key and a supported Meta Graph API version.
3. Verify the account through the account API and confirm its active status.
4. Confirm documented opt-in for that specific account, no current opt-out, approved draft,
   active campaign, and a current subscription reservation.
5. Test a Meta sandbox number with a parameter-free approved template; variable-bearing
   templates are not supported by this sender.
6. Verify delivery-status webhooks and a manual reconciliation procedure for `uncertain`
   rows before any live rollout.
7. Start one worker with dispatch enabled and inspect sanitized outcome logs. Scale gradually.

## Safety behavior

- A current subscription/quota reservation and `WhatsAppSendPolicy` are checked immediately
  before a provider request.
- The worker resolves credentials only for the active tenant-scoped account.
- The Meta adapter makes one request only. Definite provider rejection releases a still-reserved
  quota unit; confirmed sends and uncertain outcomes consume the reservation.
- A timeout, transport failure, provider 5xx/rate limit, malformed success, or unexpected
  exception after entering the sender becomes `uncertain`; it is never automatically retried.
- A stale lease cannot overwrite a newer claim. Expired processing leases are marked uncertain.
- Logs omit recipient, message body, token, provider response body and exception details.
- A worker-level failure after claim attempts to mark the delivery uncertain; if database state
  cannot be updated, lease-expiry recovery handles it later.

## Run locally

From `backend/`, with migrations applied and configuration verified:

```sh
export WHATSAPP_DISPATCH_ENABLED=true
python -m app.workers.whatsapp_dispatch_worker
```

Do not enable the flag in production until Meta acceptance, billing reconciliation, webhook
status reconciliation, backup/restore and incident runbooks have been tested. CI passing does
not mean these external acceptance steps have been completed.
