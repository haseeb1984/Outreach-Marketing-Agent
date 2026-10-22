CREATE TABLE IF NOT EXISTS whatsapp_contact_preferences (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES workspace_whatsapp_accounts(id) ON DELETE CASCADE,
    wa_id VARCHAR(64) NOT NULL,
    opted_out_at TIMESTAMPTZ,
    opted_in_at TIMESTAMPTZ,
    last_opt_out_message_id VARCHAR(256),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, account_id, wa_id),
    CHECK (wa_id ~ '^[0-9]{1,64}$')
);
CREATE INDEX IF NOT EXISTS whatsapp_contact_preferences_opted_out ON whatsapp_contact_preferences(workspace_id, wa_id) WHERE opted_out_at IS NOT NULL;
INSERT INTO schema_migrations (version) VALUES ('024_whatsapp_contact_preferences.sql') ON CONFLICT (version) DO NOTHING;
