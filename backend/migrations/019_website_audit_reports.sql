-- Persist bounded read-only website audit reports per workspace.
CREATE TABLE IF NOT EXISTS website_audit_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    start_url TEXT NOT NULL CHECK (length(start_url) BETWEEN 8 AND 2048 AND start_url ~* '^https://'),
    status TEXT NOT NULL CHECK (status IN ('completed','crawl_skipped')),
    report JSONB NOT NULL CHECK (jsonb_typeof(report)='object' AND length(report::text) <= 2000000),
    requested_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS website_audit_reports_workspace_recent_idx
    ON website_audit_reports (workspace_id, created_at DESC, id);
