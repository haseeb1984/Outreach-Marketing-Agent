-- Short-lived OAuth handshakes only. The PKCE verifier itself must live in a secret
-- manager; this table stores only an opaque reference, never the verifier or tokens.
CREATE TABLE IF NOT EXISTS workspace_provider_oauth_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    connection_id UUID NOT NULL REFERENCES workspace_provider_connections(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('email', 'whatsapp')),
    state_sha256 CHAR(64) NOT NULL UNIQUE CHECK (state_sha256 ~ '^[0-9a-f]{64}$'),
    pkce_challenge TEXT NOT NULL CHECK (pkce_challenge ~ '^[A-Za-z0-9_-]{43}$'),
    verifier_secret_reference TEXT NOT NULL CHECK (
        length(btrim(verifier_secret_reference)) BETWEEN 1 AND 500
        AND verifier_secret_reference !~* '(token|password|secret)='
    ),
    redirect_uri TEXT NOT NULL CHECK (
        length(redirect_uri) BETWEEN 10 AND 2048
        AND redirect_uri ~ '^https://'
        AND redirect_uri !~ '[[:space:]]'
    ),
    nonce_sha256 CHAR(64) NOT NULL CHECK (nonce_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CHECK (expires_at > created_at AND expires_at <= created_at + interval '15 minutes')
);
CREATE INDEX IF NOT EXISTS workspace_provider_oauth_transactions_expiry_idx
  ON workspace_provider_oauth_transactions (expires_at)
  WHERE consumed_at IS NULL;
CREATE INDEX IF NOT EXISTS workspace_provider_oauth_transactions_workspace_idx
  ON workspace_provider_oauth_transactions (workspace_id, created_at DESC);
