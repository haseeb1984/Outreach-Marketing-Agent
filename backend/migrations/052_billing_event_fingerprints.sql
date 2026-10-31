-- Store a one-way digest of the normalized verified subscription snapshot.
-- Legacy rows remain nullable and continue using their historical identity tuple.
ALTER TABLE billing_provider_events
    ADD COLUMN IF NOT EXISTS event_fingerprint TEXT;
