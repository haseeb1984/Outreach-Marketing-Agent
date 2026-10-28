# WhatsApp credential resolver

The outbound sender must resolve credentials by the exact workspace and account ID immediately before a send. `WhatsAppCredentialStore` reads only active accounts with encrypted credentials, decrypts using AES-GCM and the existing `workspace-whatsapp-account:{workspace_id}:{account_id}` authenticated-data format, and returns a typed object that is never serialized by the API.

## Fail-closed behavior

- Missing, malformed, or non-32-byte encryption keys are rejected.
- Missing/inactive accounts and missing credentials are rejected.
- Authentication-tag failure, wrong workspace/account AAD, malformed ciphertext, invalid token text, and malformed Meta asset IDs are rejected with sanitized error codes.
- Ciphertext and access tokens are not logged or returned by client-facing routes.
- This module does not send messages, reserve quota, claim queue rows, or grant consent. A dispatcher must re-run `WhatsAppSendPolicy`, verify queue state and quota reservation, and preserve the no-blind-retry rule for uncertain provider outcomes.

## Configuration

Set `PROVIDER_CREDENTIAL_ENCRYPTION_KEY` to base64 or URL-safe base64 encoding of exactly 32 random bytes. This must be the same key used when the WhatsApp account was created; rotating it without a credential re-encryption migration makes stored credentials unreadable.
