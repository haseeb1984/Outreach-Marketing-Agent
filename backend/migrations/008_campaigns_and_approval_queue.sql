-- Campaign workspace and human-reviewed outreach drafts; no provider sending in this migration.
CREATE TABLE IF NOT EXISTS outreach_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
    client_business TEXT NOT NULL CHECK (length(trim(client_business)) BETWEEN 1 AND 240),
    client_offer TEXT NOT NULL CHECK (length(trim(client_offer)) BETWEEN 1 AND 2000),
    target_customer_profile TEXT NOT NULL CHECK (length(trim(target_customer_profile)) BETWEEN 1 AND 2000),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','paused','archived')),
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outreach_campaigns_workspace_updated_idx
    ON outreach_campaigns (workspace_id, updated_at DESC, id);

CREATE TABLE IF NOT EXISTS outreach_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL REFERENCES outreach_campaigns(id) ON DELETE CASCADE,
    prospect_id UUID NOT NULL REFERENCES crm_prospects(id) ON DELETE RESTRICT,
    channel TEXT NOT NULL CHECK (channel IN ('email','whatsapp')),
    subject TEXT CHECK (subject IS NULL OR length(subject) <= 300),
    body TEXT NOT NULL CHECK (length(trim(body)) BETWEEN 1 AND 10000),
    source_evidence_url TEXT NOT NULL CHECK (source_evidence_url ~* '^https://'),
    verified_facts_used JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(verified_facts_used) = 'array'),
    status TEXT NOT NULL DEFAULT 'pending_approval' CHECK (status IN ('pending_approval','approved','rejected')),
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    reviewed_by UUID REFERENCES app_users(id) ON DELETE RESTRICT,
    reviewed_at TIMESTAMPTZ,
    review_note TEXT CHECK (review_note IS NULL OR length(review_note) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((status = 'pending_approval' AND reviewed_by IS NULL AND reviewed_at IS NULL)
        OR (status IN ('approved','rejected') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS outreach_drafts_queue_idx
    ON outreach_drafts (workspace_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS outreach_drafts_campaign_idx
    ON outreach_drafts (campaign_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS outreach_drafts_pending_deduplicate_idx
    ON outreach_drafts (campaign_id, prospect_id, channel)
    WHERE status = 'pending_approval';

CREATE TABLE IF NOT EXISTS outreach_draft_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    draft_id UUID NOT NULL REFERENCES outreach_drafts(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    actor_id UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK (event_type IN ('created','approved','rejected')),
    note TEXT CHECK (note IS NULL OR length(note) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outreach_draft_events_workspace_created_idx
    ON outreach_draft_events (workspace_id, created_at DESC);
