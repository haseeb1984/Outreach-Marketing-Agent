-- Store provider-approved templates and the latest inbound timestamp used to
-- enforce WhatsApp's customer-service window before any future outbound sender is enabled.
ALTER TABLE whatsapp_contact_preferences
    ADD COLUMN IF NOT EXISTS last_inbound_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_inbound_message_id VARCHAR(256);

CREATE TABLE IF NOT EXISTS whatsapp_message_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES workspace_whatsapp_accounts(id) ON DELETE CASCADE,
    template_name VARCHAR(512) NOT NULL CHECK (length(trim(template_name)) > 0),
    language_code VARCHAR(32) NOT NULL CHECK (length(trim(language_code)) > 0),
    category VARCHAR(40) NOT NULL CHECK (category IN ('marketing','utility','authentication')),
    provider_template_id VARCHAR(256),
    status VARCHAR(24) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','rejected','paused')),
    provider_status VARCHAR(80),
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, template_name, language_code)
);
CREATE INDEX IF NOT EXISTS whatsapp_message_templates_eligible
    ON whatsapp_message_templates(workspace_id, account_id, status, template_name, language_code);

