-- Persist draft request idempotency independently from AI quota reservations.
-- This allows deterministic template fallback drafts when AI quota is exhausted.
ALTER TABLE outreach_drafts
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS outreach_drafts_workspace_idempotency_uidx
    ON outreach_drafts (workspace_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
