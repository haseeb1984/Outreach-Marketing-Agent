-- Preserve the exact approved WhatsApp template selected when a delivery is queued.
-- Dispatch remains disabled; these fields are metadata, not permission to send.
ALTER TABLE whatsapp_outbound_deliveries
    ADD COLUMN IF NOT EXISTS template_name VARCHAR(512),
    ADD COLUMN IF NOT EXISTS language_code VARCHAR(32);

ALTER TABLE whatsapp_outbound_deliveries
    ADD CONSTRAINT whatsapp_outbound_template_pair_check
    CHECK (
        (template_name IS NULL AND language_code IS NULL)
        OR (template_name IS NOT NULL AND btrim(template_name) <> ''
            AND language_code IS NOT NULL AND language_code ~ '^[A-Za-z0-9_-]{2,32}$')
    );
