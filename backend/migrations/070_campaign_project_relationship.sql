-- Persist an optional campaign-to-project relationship with tenant-safe referential integrity.
-- Existing campaigns remain valid and unlinked; deleting a project clears only the link.
CREATE UNIQUE INDEX IF NOT EXISTS workspace_projects_id_workspace_uidx ON workspace_projects(id, workspace_id);
ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS project_id UUID;
ALTER TABLE outreach_campaigns ADD CONSTRAINT outreach_campaigns_project_workspace_fk
    FOREIGN KEY (project_id, workspace_id) REFERENCES workspace_projects(id, workspace_id)
    ON DELETE SET NULL (project_id);
CREATE INDEX IF NOT EXISTS outreach_campaigns_project_workspace_idx
    ON outreach_campaigns(workspace_id, project_id) WHERE project_id IS NOT NULL;
