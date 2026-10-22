-- Native Meta WhatsApp webhook inbox. Payloads are isolated from public APIs and never logged.
CREATE TABLE IF NOT EXISTS meta_whatsapp_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payload_sha256 CHAR(64) NOT NULL UNIQUE,
    phone_number_id VARCHAR(128),
    event_kind VARCHAR(32) NOT NULL CHECK (event_kind IN ('messages', 'statuses', 'other')),
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    processing_error_code VARCHAR(80)
);
CREATE INDEX IF NOT EXISTS idx_meta_whatsapp_webhook_events_pending
    ON meta_whatsapp_webhook_events (received_at, id)
    WHERE processed_at IS NULL;
INSERT INTO schema_migrations (version)
VALUES ('020_meta_whatsapp_webhook_inbox.sql')
ON CONFLICT (version) DO NOTHING;
