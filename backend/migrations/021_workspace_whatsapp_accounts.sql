-- Workspace-scoped Meta WhatsApp account registry. Credentials are encrypted at rest.
CREATE TABLE IF NOT EXISTS workspace_whatsapp_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    label VARCHAR(120) NOT NULL,
    waba_id VARCHAR(128) NOT NULL,
    phone_number_id VARCHAR(128) NOT NULL UNIQUE,
    encrypted_access_token BYTEA CHECK (encrypted_access_token IS NULL OR octet_length(encrypted_access_token) BETWEEN 29 AND 8192),
    status VARCHAR(24) NOT NULL DEFAULT 'pending_verification'
        CHECK (status IN ('pending_verification', 'active', 'disabled')),
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, label)
);
CREATE INDEX IF NOT EXISTS idx_workspace_whatsapp_accounts_workspace
    ON workspace_whatsapp_accounts (workspace_id, created_at DESC);
INSERT INTO schema_migrations (version)
VALUES ('021_workspace_whatsapp_accounts.sql')
ON CONFLICT (version) DO NOTHING;
