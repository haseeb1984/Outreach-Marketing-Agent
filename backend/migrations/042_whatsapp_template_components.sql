-- Persist Meta's approved template component schema and per-delivery variable values.
ALTER TABLE whatsapp_message_templates
    ADD COLUMN IF NOT EXISTS components JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE whatsapp_outbound_deliveries
    ADD COLUMN IF NOT EXISTS template_parameters JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Preserve safe, typed metadata for inbound WhatsApp media and interactive messages.
ALTER TABLE whatsapp_inbound_messages
    ADD COLUMN IF NOT EXISTS media_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
