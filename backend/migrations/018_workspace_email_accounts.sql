-- Tenant-scoped SMTP identities. Passwords are AES-GCM encrypted by the application.
CREATE TABLE IF NOT EXISTS workspace_email_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    label TEXT NOT NULL CHECK (length(trim(label)) BETWEEN 1 AND 120),
    smtp_host TEXT NOT NULL CHECK (length(trim(smtp_host)) BETWEEN 1 AND 253),
    smtp_port INTEGER NOT NULL DEFAULT 587 CHECK (smtp_port=587),
    smtp_username TEXT NOT NULL CHECK (length(trim(smtp_username)) BETWEEN 1 AND 320),
    encrypted_password BYTEA NOT NULL CHECK (octet_length(encrypted_password) BETWEEN 29 AND 5000),
    from_email TEXT NOT NULL CHECK (length(trim(from_email)) BETWEEN 3 AND 320),
    from_name TEXT NOT NULL DEFAULT 'Outreach Marketing Agent' CHECK (length(trim(from_name)) BETWEEN 1 AND 200),
    starttls BOOLEAN NOT NULL DEFAULT TRUE CHECK (starttls=TRUE),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id,label)
);
CREATE INDEX IF NOT EXISTS workspace_email_accounts_workspace_idx
    ON workspace_email_accounts (workspace_id,created_at DESC);
ALTER TABLE outreach_deliveries
    ADD COLUMN IF NOT EXISTS email_account_id UUID REFERENCES workspace_email_accounts(id) ON DELETE SET NULL;
