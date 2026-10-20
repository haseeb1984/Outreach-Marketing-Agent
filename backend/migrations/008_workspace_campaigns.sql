-- Workspace-scoped campaigns. Campaign URLs are stored as metadata only; this migration does not fetch them.
CREATE TABLE IF NOT EXISTS workspace_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 160),
    website_url TEXT NOT NULL CHECK (length(trim(website_url)) BETWEEN 9 AND 2048),
    goal TEXT NOT NULL CHECK (goal IN ('partnerships', 'influencer_outreach', 'sales', 'brand_awareness', 'other')),
    channel TEXT NOT NULL CHECK (channel IN ('email', 'whatsapp', 'multi_channel')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'completed', 'archived')),
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at >= starts_at)
);
CREATE INDEX IF NOT EXISTS workspace_campaigns_recent_idx
    ON workspace_campaigns (workspace_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS workspace_campaigns_status_idx
    ON workspace_campaigns (workspace_id, status, created_at DESC);

-- Link drafts to a campaign without permitting cross-workspace references.
ALTER TABLE workspace_outreach_drafts
    ADD COLUMN IF NOT EXISTS campaign_id UUID;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'workspace_outreach_drafts_campaign_workspace_fk'
    ) THEN
        ALTER TABLE workspace_outreach_drafts
            ADD CONSTRAINT workspace_outreach_drafts_campaign_workspace_fk
            FOREIGN KEY (workspace_id, campaign_id)
            REFERENCES workspace_campaigns (workspace_id, id)
            ON DELETE SET NULL (campaign_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS workspace_outreach_drafts_campaign_idx
    ON workspace_outreach_drafts (workspace_id, campaign_id, created_at DESC)
    WHERE campaign_id IS NOT NULL;
