-- Lease processing claims and make expired in-flight sends uncertain rather than retrying.
ALTER TABLE whatsapp_outbound_deliveries
    ADD COLUMN IF NOT EXISTS lease_token UUID,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS whatsapp_outbound_expired_leases
    ON whatsapp_outbound_deliveries(lease_expires_at, id)
    WHERE status='processing';
