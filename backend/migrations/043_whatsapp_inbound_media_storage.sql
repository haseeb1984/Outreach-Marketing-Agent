-- Store inbound WhatsApp attachments encrypted at application level.
ALTER TABLE whatsapp_inbound_messages
    ADD COLUMN IF NOT EXISTS media_ciphertext BYTEA,
    ADD COLUMN IF NOT EXISTS media_mime_type TEXT,
    ADD COLUMN IF NOT EXISTS media_filename TEXT,
    ADD COLUMN IF NOT EXISTS media_size BIGINT,
    ADD COLUMN IF NOT EXISTS media_downloaded_at TIMESTAMPTZ;

ALTER TABLE whatsapp_inbound_messages
    ADD CONSTRAINT whatsapp_inbound_media_size_positive
    CHECK (media_size IS NULL OR media_size BETWEEN 1 AND 16777216);
