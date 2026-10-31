-- Store a digest of each normalized verified Paddle transaction event.
-- Legacy event rows remain nullable and retain their historical identity checks.
ALTER TABLE billing_transaction_events
    ADD COLUMN IF NOT EXISTS event_fingerprint TEXT;
