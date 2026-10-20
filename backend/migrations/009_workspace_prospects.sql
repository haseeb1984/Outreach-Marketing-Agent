-- Workspace-scoped prospect CRM with explicit opt-out and auditable stage changes.
CREATE TABLE IF NOT EXISTS workspace_prospects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL,
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) BETWEEN 1 AND 200),
    organization_name TEXT CHECK (organization_name IS NULL OR length(trim(organization_name)) <= 200),
    website_url TEXT NOT NULL CHECK (length(trim(website_url)) BETWEEN 9 AND 2048),
    contact_email TEXT CHECK (contact_email IS NULL OR length(contact_email) <= 320),
    contact_phone TEXT CHECK (contact_phone IS NULL OR length(contact_phone) <= 40),
    source_url TEXT NOT NULL CHECK (length(trim(source_url)) BETWEEN 9 AND 2048),
    fit_reason TEXT NOT NULL CHECK (length(trim(fit_reason)) BETWEEN 1 AND 2000),
    stage TEXT NOT NULL DEFAULT 'researched'
      CHECK (stage IN ('researched','qualified','drafting','contacted','replied','meeting','customer','not_a_fit','opted_out')),
    opt_out BOOLEAN NOT NULL DEFAULT FALSE,
    opt_out_at TIMESTAMPTZ,
    notes TEXT CHECK (notes IS NULL OR length(notes) <= 4000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    FOREIGN KEY (workspace_id, campaign_id)
      REFERENCES workspace_campaigns (workspace_id, id) ON DELETE CASCADE,
    CHECK ((opt_out = FALSE AND opt_out_at IS NULL) OR (opt_out = TRUE AND opt_out_at IS NOT NULL)),
    CHECK (opt_out = FALSE OR stage = 'opted_out')
);
CREATE INDEX IF NOT EXISTS workspace_prospects_campaign_idx
  ON workspace_prospects (workspace_id, campaign_id, stage, created_at DESC);
CREATE INDEX IF NOT EXISTS workspace_prospects_email_idx
  ON workspace_prospects (workspace_id, lower(contact_email))
  WHERE contact_email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS workspace_prospects_dedupe_email_idx
  ON workspace_prospects (workspace_id, campaign_id, lower(contact_email))
  WHERE contact_email IS NOT NULL;
