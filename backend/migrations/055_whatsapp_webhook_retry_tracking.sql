-- Durable retry tracking for the Meta WhatsApp webhook inbox.
-- Failed transactions roll back their in-transaction claim counter, so the worker
-- increments attempts in its post-rollback failure handler. Exhausted events are
-- retained for inspection and excluded from automatic processing at attempt 8.
ALTER TABLE meta_whatsapp_webhook_events
    ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS dead_lettered_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='meta_whatsapp_webhook_events'::regclass
          AND conname='meta_whatsapp_webhook_events_attempts_nonnegative'
    ) THEN
        ALTER TABLE meta_whatsapp_webhook_events
            ADD CONSTRAINT meta_whatsapp_webhook_events_attempts_nonnegative
            CHECK (attempts >= 0);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_meta_whatsapp_webhook_events_retryable
    ON meta_whatsapp_webhook_events (received_at, id)
    WHERE processed_at IS NULL AND attempts < 8;

CREATE INDEX IF NOT EXISTS idx_meta_whatsapp_webhook_events_dead_lettered
    ON meta_whatsapp_webhook_events (dead_lettered_at, id)
    WHERE dead_lettered_at IS NOT NULL;
