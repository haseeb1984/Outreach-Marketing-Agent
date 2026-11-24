-- Allow each workspace project to manage its own WordPress site while retaining
-- the existing workspace-level connection as a backward-compatible fallback.
ALTER TABLE workspace_wordpress_connections
    ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES workspace_projects(id) ON DELETE CASCADE;

ALTER TABLE workspace_wordpress_connections
    DROP CONSTRAINT IF EXISTS workspace_wordpress_connections_workspace_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS workspace_wordpress_connections_workspace_fallback_uidx
    ON workspace_wordpress_connections(workspace_id)
    WHERE project_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS workspace_wordpress_connections_project_uidx
    ON workspace_wordpress_connections(workspace_id, project_id)
    WHERE project_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS workspace_wordpress_connections_project_status_idx
    ON workspace_wordpress_connections(workspace_id, project_id, status);
