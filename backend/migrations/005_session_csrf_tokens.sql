-- Bind each browser session to a server-stored CSRF token digest.
-- Existing sessions cannot have a synchronizer token retroactively issued, so revoke them.
ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS csrf_token_sha256 CHAR(64);
UPDATE auth_sessions
   SET revoked_at = COALESCE(revoked_at, now()),
       csrf_token_sha256 = repeat('0', 64)
 WHERE csrf_token_sha256 IS NULL;
ALTER TABLE auth_sessions ALTER COLUMN csrf_token_sha256 SET NOT NULL;
ALTER TABLE auth_sessions
  ADD CONSTRAINT auth_sessions_csrf_digest_format
  CHECK (csrf_token_sha256 ~ '^[0-9a-f]{64}$');
