-- Link drafts to a workspace-local CRM prospect without permitting cross-workspace references.
ALTER TABLE workspace_outreach_drafts
  ADD COLUMN IF NOT EXISTS prospect_id UUID;
DO $migration$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'workspace_outreach_drafts_workspace_prospect_fk'
      AND conrelid = 'workspace_outreach_drafts'::regclass
  ) THEN
    ALTER TABLE workspace_outreach_drafts
      ADD CONSTRAINT workspace_outreach_drafts_workspace_prospect_fk
      FOREIGN KEY (workspace_id, prospect_id)
      REFERENCES workspace_prospects (workspace_id, id)
      ON DELETE RESTRICT;
  END IF;
END;
$migration$;
CREATE INDEX IF NOT EXISTS workspace_outreach_drafts_prospect_idx
  ON workspace_outreach_drafts (workspace_id, prospect_id, created_at DESC)
  WHERE prospect_id IS NOT NULL;
