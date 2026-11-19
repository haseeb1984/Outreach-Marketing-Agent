-- Keep the composite tenant-integrity foreign key aligned with the established
-- workspace cascade behavior. The older single-column FK already cascades, but a
-- composite RESTRICT constraint would otherwise block deletion of tenant drafts.
ALTER TABLE outreach_deliveries
    DROP CONSTRAINT IF EXISTS outreach_deliveries_draft_workspace_fk;

ALTER TABLE outreach_deliveries
    ADD CONSTRAINT outreach_deliveries_draft_workspace_fk
    FOREIGN KEY (draft_id, workspace_id)
    REFERENCES outreach_drafts(id, workspace_id)
    ON DELETE CASCADE;
