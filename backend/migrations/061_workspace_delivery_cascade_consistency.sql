-- Keep composite tenant-integrity foreign keys aligned with established workspace
-- cascade behavior. RESTRICT constraints can block deleting a tenant's own graph.
ALTER TABLE outreach_deliveries
    DROP CONSTRAINT IF EXISTS outreach_deliveries_draft_workspace_fk;
ALTER TABLE outreach_deliveries
    ADD CONSTRAINT outreach_deliveries_draft_workspace_fk
    FOREIGN KEY (draft_id, workspace_id)
    REFERENCES outreach_drafts(id, workspace_id)
    ON DELETE CASCADE;

-- Drafts are workspace-owned and must be removable with their prospects. The old
-- single-column FK was RESTRICT and the tenant-composite FK was NO ACTION.
ALTER TABLE outreach_drafts
    DROP CONSTRAINT IF EXISTS outreach_drafts_prospect_id_fkey;
ALTER TABLE outreach_drafts
    ADD CONSTRAINT outreach_drafts_prospect_id_fkey
    FOREIGN KEY (prospect_id)
    REFERENCES crm_prospects(id)
    ON DELETE CASCADE;

ALTER TABLE outreach_drafts
    DROP CONSTRAINT IF EXISTS outreach_drafts_prospect_workspace_fk;
ALTER TABLE outreach_drafts
    ADD CONSTRAINT outreach_drafts_prospect_workspace_fk
    FOREIGN KEY (prospect_id, workspace_id)
    REFERENCES crm_prospects(id, workspace_id)
    ON DELETE CASCADE;
