CREATE TABLE IF NOT EXISTS outreach_deliveries (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 draft_id UUID NOT NULL UNIQUE REFERENCES outreach_drafts(id) ON DELETE RESTRICT,
 channel TEXT NOT NULL CHECK(channel IN ('email','whatsapp')),
 idempotency_key TEXT NOT NULL CHECK(length(idempotency_key) BETWEEN 8 AND 200),
 status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','processing','sent','failed','cancelled')),
 attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count BETWEEN 0 AND 100),
 provider_message_id TEXT,
 error_code TEXT CHECK(error_code IS NULL OR length(error_code)<=100),
 queued_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 processing_at TIMESTAMPTZ,
 sent_at TIMESTAMPTZ,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(workspace_id,idempotency_key),
 CHECK((status='sent' AND sent_at IS NOT NULL) OR status<>'sent')
);
CREATE INDEX IF NOT EXISTS outreach_deliveries_workspace_queue_idx ON outreach_deliveries(workspace_id,status,queued_at DESC);
