# Provider connection foundation

## Current implementation boundary

Migration 012 stores **connection metadata only** for workspace-owned email and WhatsApp provider accounts. It does not implement OAuth, provider webhooks, token refresh, provider API calls, or message delivery.

## Secret handling

- Provider credentials must be stored in a dedicated secret manager, never as raw access/refresh tokens in PostgreSQL.
- `secret_reference` is an opaque server-side reference, not a credential. Never return it from customer-facing APIs or write it to logs.
- A connection must remain `pending` until a real provider authorization flow validates it.
- `connected` must only be set after provider-side validation; manual metadata entry is not proof of connectivity.
- Revoke access by changing state and scheduling deletion/revocation of the external credential in the provider/secret manager.
- Do not log authorization codes, tokens, full callback URLs, or provider payloads containing personal data.

## Lifecycle

`pending -> connected -> revoked`; validation failures may set `error`. Revoked connections are not reused. Reconnecting should create a new connection record after provider authorization.

## Release gate

Before exposing connect/disconnect endpoints, implement OAuth state and PKCE where supported, exact redirect URI allowlisting, CSRF protection, workspace-admin authorization, encrypted secret-manager storage, callback replay protection, provider webhook signature checks, token refresh/expiry handling, and integration tests. Until then, sending remains disabled.
