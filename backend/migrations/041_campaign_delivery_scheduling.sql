-- Persist operator-selected delivery times; only approved drafts can enter this queue.
ALTER TABLE outreach_deliveries
    ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS outreach_deliveries_due_idx
    ON outreach_deliveries (scheduled_at, queued_at, id)
    WHERE status = 'queued';
