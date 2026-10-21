-- Tenant-scoped prospect CRM foundation. Contact data is intentionally minimal and evidence-led.
CREATE TABLE IF NOT EXISTS crm_prospects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
    company TEXT NOT NULL CHECK (length(trim(company)) BETWEEN 1 AND 240),
    role TEXT CHECK (role IS NULL OR length(trim(role)) <= 160),
    contact_email TEXT CHECK (contact_email IS NULL OR (length(contact_email) <= 320 AND contact_email = trim(contact_email))),
    website_url TEXT NOT NULL CHECK (length(trim(website_url)) BETWEEN 8 AND 2048),
    evidence_url TEXT NOT NULL CHECK (length(trim(evidence_url)) BETWEEN 8 AND 2048),
    evidence_observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fit_reason TEXT NOT NULL CHECK (length(trim(fit_reason)) BETWEEN 1 AND 2000),
    verified_facts JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(verified_facts) = 'array'),
    stage TEXT NOT NULL DEFAULT 'new' CHECK (stage IN ('new','qualified','approved','contacted','replied','converted','disqualified','do_not_contact')),
    notes TEXT NOT NULL DEFAULT '' CHECK (length(notes) <= 5000),
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at TIMESTAMPTZ,
    CHECK (website_url ~* '^https://'),
    CHECK (evidence_url ~* '^https://')
);
CREATE INDEX IF NOT EXISTS crm_prospects_workspace_updated_idx
    ON crm_prospects (workspace_id, updated_at DESC, id)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS crm_prospects_workspace_stage_idx
    ON crm_prospects (workspace_id, stage, updated_at DESC)
    WHERE archived_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS crm_prospects_workspace_evidence_unique
    ON crm_prospects (workspace_id, lower(evidence_url))
    WHERE archived_at IS NULL;
