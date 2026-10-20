# Provider connection foundation

## Current implementation boundary

Migration 012 stores **connection metadata only** for workspace-owned email and WhatsApp provider accounts. The API can create an admin-authorized `pending` intent, list safe metadata, and cancel a pending intent. Cancellation marks only a pending metadata record as revoked; it does not claim to revoke a live provider credential. It does not implement OAuth, provider webhooks, token refresh, provider API calls, or message delivery.

## Secret handling

- Provider credentials must be stored in a dedicated secret manager, never as raw access/refresh tokens in PostgreSQL.
- `secret_reference` is an opaque server-side reference, not a credential. Never return it from customer-facing APIs or write it to logs.
- A connection must remain `pending` until a real provider authorization flow validates it.
- `connected` must only be set after provider-side validation; manual metadata entry is not proof of connectivity.
- Revoke access by changing state and scheduling deletion/revocation of the external credential in the provider/secret manager.
- Do not log authorization codes, tokens, full callback URLs, or provider payloads.

## Secret manager adapter contract

`app.services.secret_manager` defines the asynchronous `SecretManager` protocol with `put`, `get`, and `delete`. Its default `UnconfiguredSecretManager` fails closed for every operation; it does not silently fall back to plaintext files, environment variables, or the application database. A deployment must explicitly wire an approved managed-vault implementation before OAuth can begin.

Secret references are validated as opaque identifiers before persistence. The validation rejects inline credential assignments, URL-like values, whitespace, traversal-like paths, and overlong references. The adapter must additionally enforce purpose separation, access policy, encryption at rest, rotation, and audit controls. This contract alone is not a production secret vault.

## OAuth protocol primitives and release gates

The OAuth security helpers generate PKCE S256 pairs, require exact configured HTTPS callback allowlisting, validate callback parameter shape, and compare nonce digests in constant time. OAuth is still **not live**: no public callback route, provider-specific adapter, token exchange, provider identity validation, refresh, or sending path is enabled.

Before enabling a provider, implement and test all of the following:

1. Approved secret manager adapter and deployment configuration.
2. Exact callback URI allowlist per provider and environment.
3. Provider-specific issuer/audience/nonce validation and OAuth error handling.
4. Authorization-code exchange over verified TLS and account identity validation.
5. Least-privilege scope validation and credential revocation/rotation.
6. Provider sandbox integration tests, including rejected state, replay, expiry, wrong workspace, and failure cleanup.
7. Security review confirming no credentials, authorization codes, or callback query values reach logs.
