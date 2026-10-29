-- Make report persistence idempotent across worker lease loss/retries.
-- A completed report remains available if its queue row is later deleted.
ALTER TABLE website_audit_reports
    ADD COLUMN IF NOT EXISTS job_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'website_audit_reports_job_id_fkey'
          AND conrelid = 'website_audit_reports'::regclass
    ) THEN
        ALTER TABLE website_audit_reports
            ADD CONSTRAINT website_audit_reports_job_id_fkey
            FOREIGN KEY (job_id) REFERENCES workspace_jobs(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS website_audit_reports_job_id_unique_idx
    ON website_audit_reports (job_id)
    WHERE job_id IS NOT NULL;
