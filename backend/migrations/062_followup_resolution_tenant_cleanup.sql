-- Follow-up delivery resolutions are immutable to ordinary application operations,
-- but remain tenant-owned records and must cascade with their workspace graph.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM outreach_followup_delivery_resolutions r
        LEFT JOIN workspaces w ON w.id=r.workspace_id
        WHERE w.id IS NULL
    ) THEN
        RAISE EXCEPTION 'orphaned_followup_delivery_resolution_workspace';
    END IF;
END $$;

ALTER TABLE outreach_followup_delivery_resolutions
    DROP CONSTRAINT IF EXISTS outreach_followup_delivery_resolutions_enrollment_id_fkey;
ALTER TABLE outreach_followup_delivery_resolutions
    ADD CONSTRAINT outreach_followup_delivery_resolutions_enrollment_id_fkey
    FOREIGN KEY (enrollment_id)
    REFERENCES outreach_followup_enrollments(id)
    ON DELETE CASCADE;

ALTER TABLE outreach_followup_delivery_resolutions
    DROP CONSTRAINT IF EXISTS outreach_followup_delivery_resolutions_draft_id_fkey;
ALTER TABLE outreach_followup_delivery_resolutions
    ADD CONSTRAINT outreach_followup_delivery_resolutions_draft_id_fkey
    FOREIGN KEY (draft_id)
    REFERENCES outreach_drafts(id)
    ON DELETE CASCADE;

ALTER TABLE outreach_followup_delivery_resolutions
    ADD CONSTRAINT outreach_followup_delivery_resolutions_workspace_id_fkey
    FOREIGN KEY (workspace_id)
    REFERENCES workspaces(id)
    ON DELETE CASCADE;

-- Preserve append-only behavior for direct application deletes/updates while allowing
-- referential-action deletes initiated by a parent workspace/tenant cascade.
CREATE OR REPLACE FUNCTION prevent_followup_delivery_resolution_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'follow-up delivery resolution records are immutable';
END;
$$;
