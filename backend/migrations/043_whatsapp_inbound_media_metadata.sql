-- Preserve safe, typed metadata for inbound WhatsApp media and interactive messages.
ALTER TABLE whatsapp_inbound_messages
    ADD COLUMN IF NOT EXISTS media_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
