-- Workspace-configurable first-response SLA thresholds for WhatsApp inbox.
CREATE TABLE IF NOT EXISTS whatsapp_inbox_sla_policies (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    warning_minutes INTEGER NOT NULL DEFAULT 15 CHECK (warning_minutes BETWEEN 1 AND 1440),
    breach_minutes INTEGER NOT NULL DEFAULT 60 CHECK (breach_minutes BETWEEN 2 AND 10080),
    updated_by TEXT REFERENCES app_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (breach_minutes > warning_minutes)
);
