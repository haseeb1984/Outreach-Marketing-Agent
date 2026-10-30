-- Durable provider feedback ledger and normalized email delivery state.
ALTER TABLE outreach_deliveries
    ADD COLUMN IF NOT EXISTS provider_status TEXT
      CHECK (provider_status IS NULL OR provider_status IN ('delivered','deferred','bounced','complained','unsubscribed')),
    ADD COLUMN IF NOT EXISTS provider_status_at TIMESTAMPTZ;

ALTER TABLE outreach_contact_controls
    ADD COLUMN IF NOT EXISTS email_suppression_reason TEXT
      CHECK (email_suppression_reason IS NULL OR email_suppression_reason IN ('manual','unsubscribe','hard_bounce','spam_complaint')),
    ADD COLUMN IF NOT EXISTS email_suppressed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS email_provider_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 80),
    provider_event_id TEXT NOT NULL CHECK (length(trim(provider_event_id)) BETWEEN 1 AND 300),
    delivery_id UUID NOT NULL REFERENCES outreach_deliveries(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('delivered','deferred','bounced','complained','unsubscribed')),
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(provider,provider_event_id)
);
CREATE INDEX IF NOT EXISTS email_provider_events_delivery_idx
    ON email_provider_events(delivery_id,occurred_at DESC);
CREATE INDEX IF NOT EXISTS outreach_deliveries_provider_status_idx
    ON outreach_deliveries(workspace_id,provider_status,provider_status_at DESC)
    WHERE provider_status IS NOT NULL;
