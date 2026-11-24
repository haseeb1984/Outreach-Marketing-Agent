-- Workspace-scoped WordPress connections and auditable article delivery state.
CREATE TABLE IF NOT EXISTS workspace_wordpress_connections (
    id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    site_url TEXT NOT NULL,
    username TEXT NOT NULL,
    encrypted_application_password BYTEA,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','verified','disabled')),
    verified_at TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id)
);

ALTER TABLE website_content_briefs
    ADD COLUMN IF NOT EXISTS cms_connection_id UUID REFERENCES workspace_wordpress_connections(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS cms_post_id BIGINT,
    ADD COLUMN IF NOT EXISTS cms_post_url TEXT,
    ADD COLUMN IF NOT EXISTS cms_status TEXT NOT NULL DEFAULT 'not_sent'
        CHECK (cms_status IN ('not_sent','sending','draft_created','publishing','published','failed')),
    ADD COLUMN IF NOT EXISTS cms_last_error TEXT,
    ADD COLUMN IF NOT EXISTS cms_synced_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_content_briefs_cms_status
    ON website_content_briefs(workspace_id,cms_status,updated_at DESC);
