-- Tenant-mapped WhatsApp conversation records. Inbound events are deduplicated by provider message ID.
CREATE TABLE IF NOT EXISTS whatsapp_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES workspace_whatsapp_accounts(id) ON DELETE CASCADE,
    prospect_id UUID REFERENCES crm_prospects(id) ON DELETE SET NULL,
    wa_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, account_id, wa_id)
);
CREATE INDEX IF NOT EXISTS whatsapp_conversations_workspace_updated
    ON whatsapp_conversations(workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS whatsapp_inbound_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES whatsapp_conversations(id) ON DELETE CASCADE,
    provider_message_id VARCHAR(256) NOT NULL UNIQUE,
    message_type VARCHAR(40) NOT NULL,
    text_body TEXT,
    provider_timestamp TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (text_body IS NULL OR length(text_body) <= 10000)
);
CREATE INDEX IF NOT EXISTS whatsapp_inbound_messages_conversation
    ON whatsapp_inbound_messages(conversation_id, received_at DESC);

CREATE TABLE IF NOT EXISTS whatsapp_delivery_status_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES workspace_whatsapp_accounts(id) ON DELETE CASCADE,
    provider_message_id VARCHAR(256) NOT NULL,
    recipient_wa_id VARCHAR(64),
    status VARCHAR(40) NOT NULL,
    provider_timestamp TIMESTAMPTZ,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(errors) = 'array'),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider_message_id, status, provider_timestamp)
);
CREATE INDEX IF NOT EXISTS whatsapp_delivery_status_account_received
    ON whatsapp_delivery_status_events(account_id, received_at DESC);

ALTER TABLE meta_whatsapp_webhook_events
    ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ;
ALTER TABLE meta_whatsapp_webhook_events
    ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0);

INSERT INTO schema_migrations (version)
VALUES ('023_whatsapp_conversations_and_status.sql')
ON CONFLICT (version) DO NOTHING;
