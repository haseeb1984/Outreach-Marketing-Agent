-- Link CRM prospects to client projects without changing existing records.
-- The composite foreign key prevents cross-workspace project references.
ALTER TABLE crm_prospects ADD COLUMN IF NOT EXISTS project_id UUID;
ALTER TABLE crm_prospects ADD CONSTRAINT crm_prospects_project_workspace_fk
    FOREIGN KEY (project_id, workspace_id) REFERENCES workspace_projects(id, workspace_id)
    ON DELETE SET NULL (project_id);
CREATE INDEX IF NOT EXISTS crm_prospects_project_workspace_idx
    ON crm_prospects(workspace_id, project_id) WHERE project_id IS NOT NULL;
