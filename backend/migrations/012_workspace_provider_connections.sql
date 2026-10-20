-- Provider connection metadata only. OAuth tokens and API secrets belong in a secret manager,
-- never in this table or in customer-facing API payloads.
CREATE TABLE IF NOT EXISTS workspace_provider_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('email', 'whatsapp')),
    provider_account_id TEXT,
    display_label TEXT NOT NULL CHECK (length(btrim(display_label)) BETWEEN 1 AND 160),
    status TEXT NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending', 'connected', 'revoked', 'error')),
    secret_reference TEXT,
    granted_scopes TEXT[] NOT NULL DEFAULT '{}',
    token_expires_at TIMESTAMPTZ,
    last_validated_at TIMESTAMPTZ,
    last_error_code TEXT,
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    CONSTRAINT workspace_provider_connections_secret_reference_check
      CHECK (secret_reference IS NULL OR
        (length(btrim(secret_reference)) BETWEEN 1 AND 500
         AND secret_reference !~* '(token|password|secret)='))
);
CREATE INDEX IF NOT EXISTS workspace_provider_connections_workspace_idx
  ON workspace_provider_connections (workspace_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS workspace_provider_connections_provider_account_idx
  ON workspace_provider_connections (workspace_id, provider, provider_account_id)
  WHERE provider_account_id IS NOT NULL AND status <> 'revoked';
