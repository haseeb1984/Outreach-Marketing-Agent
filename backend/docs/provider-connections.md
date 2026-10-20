# Provider connection foundation

## Current implementation boundary

Migration 012 stores **connection metadata only** for workspace-owned email and WhatsApp provider accounts. The API can create an admin-authorized `pending` intent, list safe metadata, and cancel a pending intent. Cancellation marks only a pending metadata record as revoked; it does not claim to revoke a live provider credential. It does not implement OAuth, provider webhooks, token refresh, provider API calls, or message delivery.

## Secret handling

- Provider credentials must be stored in a dedicated secret manager, never as raw access/refresh tokens in PostgreSQL.
- `secret_reference` is an opaque server-side reference, not a credential. Never return it from customer-facing APIs or write it to logs.
- A connection must remain `pending` until a real provider authorization flow validates it.
- `connected` must only be set after provider-side validation; manual metadata entry is not proof of connectivity.
- Revoke access by changing state and scheduling deletion/revocation of the external credential in the provider/secret manager.
- Do not log authorization codes, tokens, full callback URLs, or provider payloads containing personal data.

## Lifecycle

Current API behavior is limited to creating `pending` intent records and listing safe metadata. No customer-facing endpoint can set `connected`, `error`, or `revoked`. When implemented, the intended lifecycle is `pending -> connected -> revoked`; validation failures may set `error`. Revoked connections must not be reused. Reconnecting should create a new record after provider authorization.

## Release gate

Before adding real connect/disconnect behavior, implement OAuth state and PKCE where supported, exact redirect URI allowlisting, CSRF protection, workspace-admin authorization, encrypted secret-manager storage, callback replay protection, provider webhook signature checks, token refresh/expiry handling, credential revocation, and integration tests. The current intent/list endpoints are not proof of a connection. Until the full release gate passes, sending remains disabled.


## Inspecting one connection

Workspace viewers and above can retrieve a single connection's metadata with
`GET /api/v1/workspaces/{workspace_id}/provider-connections/{connection_id}`.
The lookup is scoped to both the workspace and connection ID; an unknown ID and an
ID belonging to another workspace both return `404`. The response uses the same
safe metadata allowlist as the list endpoint and always reports
`sending_enabled: false`. It does not reveal secret-manager references or provider
credentials, and it does not imply that the provider account is authorized.
