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

The OAuth security helpers generate PKCE S256 pairs, require exact configured HTTPS callback allowlisting, validate callback parameter shape, and compare nonce digests in constant time. The transaction store now requires an explicit `allowed_redirect_uris` list, validates the callback against that list before touching the database, validates opaque secret-manager references, and rejects malformed state/nonce shapes before persistence. The store persists only state and nonce digests and supports atomic one-time consumption with expiry. Focused tests verify rejection happens before database access. OAuth is still **not live**: no public callback route, provider-specific adapter, token exchange, provider identity validation, refresh, or sending path is enabled.

Before enabling a provider, implement and test all of the following:

1. Approved secret manager adapter and deployment configuration.
2. Exact callback URI allowlist per provider and environment.
3. Provider-specific issuer/audience/nonce validation and OAuth error handling.
4. Authorization-code exchange over verified TLS and account identity validation.
5. Least-privilege scope validation and credential revocation/rotation.
6. Provider sandbox integration tests, including rejected state, replay, expiry, wrong workspace, and failure cleanup.
7. Security review confirming no credentials, authorization codes, or callback query values reach logs.


## Provider adapter contract

`app.services.provider_oauth_adapter` now defines the provider configuration model, adapter protocol, verified-identity result shape, and an explicit registry. Configuration validation requires HTTPS authorization/token endpoints, exact HTTPS callback allowlists, bounded provider IDs/client identifiers, and a non-empty constrained scope allowlist. An empty registry rejects all provider lookups rather than guessing an adapter.

This is a contract only, not a live integration. Before a concrete adapter is registered, it must build authorization requests from server-generated state/PKCE/nonce values, exchange codes over verified TLS, validate issuer and audience where applicable, verify nonce and account identity, and return only verified account ID and granted scopes. Do not register a stub or test adapter in production.

## Authorization-start and callback orchestration status

The backend now has service-layer orchestration for authorization start and callback validation:

- `WorkspaceProviderOAuthStartService` generates server-side PKCE/state/nonce material, validates requested scopes against the configured allowlist, persists a short-lived transaction, and rejects authorization URLs whose HTTPS origin/path differs from the configured provider endpoint.
- `WorkspaceProviderOAuthCallbackService` consumes state once, validates callback shape, retrieves the PKCE verifier by purpose-bound secret reference, delegates code exchange and provider-specific identity validation to an explicitly registered adapter, and returns verified identity metadata only.
- The orchestration services are not yet wired into public API routes or production dependency configuration. No concrete email or WhatsApp provider adapter is registered by default, and the default secret manager remains unavailable. Therefore these additions do **not** make OAuth or sending live.

### Required integration gates

Before adding a route that calls these services, the route must require an authenticated session, admin-level workspace membership, CSRF validation for state-changing requests, and rate limiting. It must verify that the connection intent belongs to the same workspace and provider before starting authorization. Callback completion must never trust a workspace or connection ID supplied by the browser; it must use only the consumed server-side transaction. A verified identity is not sufficient to mark a connection connected until credentials have been stored through the approved secret manager and the connection metadata update succeeds transactionally.

The deployment must also validate the generated authorization URL's query parameters against the exact server-generated state, PKCE challenge/method, nonce, and redirect URI before returning it to the browser. Any callback failure must leave sending disabled, consume the transaction, and avoid exposing provider response bodies or credentials.
