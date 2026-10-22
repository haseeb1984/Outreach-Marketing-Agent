-- Workspace-scoped client projects for multi-website growth workflows.
CREATE TABLE IF NOT EXISTS workspace_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 160),
    website_url TEXT CHECK (website_url IS NULL OR (length(trim(website_url)) BETWEEN 8 AND 2048 AND website_url ~* '^https://')),
    business_model TEXT NOT NULL DEFAULT '' CHECK (length(business_model) <= 120),
    target_market TEXT NOT NULL DEFAULT '' CHECK (length(target_market) <= 240),
    language TEXT NOT NULL DEFAULT '' CHECK (length(language) <= 120),
    audience TEXT NOT NULL DEFAULT '' CHECK (length(audience) <= 2000),
    offer TEXT NOT NULL DEFAULT '' CHECK (length(offer) <= 2000),
    conversion_goal TEXT NOT NULL DEFAULT '' CHECK (length(conversion_goal) <= 300),
    brand_voice TEXT NOT NULL DEFAULT '' CHECK (length(brand_voice) <= 800),
    competitors JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(competitors) = 'array'),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS workspace_projects_workspace_updated_idx
    ON workspace_projects (workspace_id, updated_at DESC, id)
    WHERE archived_at IS NULL;
