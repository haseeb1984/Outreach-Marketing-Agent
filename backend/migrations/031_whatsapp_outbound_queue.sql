-- Durable, idempotent WhatsApp outbound queue. This migration does not enable dispatch.
CREATE TABLE IF NOT EXISTS whatsapp_outbound_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES workspace_whatsapp_accounts(id) ON DELETE RESTRICT,
    draft_id UUID NOT NULL REFERENCES outreach_drafts(id) ON DELETE RESTRICT,
    prospect_id UUID NOT NULL REFERENCES crm_prospects(id) ON DELETE RESTRICT,
    idempotency_key VARCHAR(200) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','processing','sent','delivered','read','failed','uncertain','cancelled')),
    provider_message_id VARCHAR(256),
    error_code VARCHAR(100),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    queued_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processing_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, idempotency_key),
    UNIQUE (workspace_id, draft_id)
);
CREATE INDEX IF NOT EXISTS whatsapp_outbound_queue_pending
    ON whatsapp_outbound_deliveries(status, queued_at, id)
    WHERE status='queued';
CREATE INDEX IF NOT EXISTS whatsapp_outbound_workspace_history
    ON whatsapp_outbound_deliveries(workspace_id, queued_at DESC, id);
INSERT INTO schema_migrations (version)
VALUES ('031_whatsapp_outbound_queue.sql')
ON CONFLICT (version) DO NOTHING;
