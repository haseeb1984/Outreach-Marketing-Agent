-- Add the durable one-time password reset token store.
-- Raw tokens are never persisted; only SHA-256 digests are stored.
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id bigserial PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    token_sha256 text NOT NULL UNIQUE
        CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    CHECK (expires_at > created_at),
    CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE INDEX IF NOT EXISTS password_reset_tokens_user_live_idx
    ON password_reset_tokens (user_id, expires_at)
    WHERE consumed_at IS NULL;

CREATE INDEX IF NOT EXISTS password_reset_tokens_expiry_idx
    ON password_reset_tokens (expires_at);

-- The migration runner records this filename after the SQL succeeds.
