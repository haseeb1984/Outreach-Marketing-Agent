-- Persistent, workspace-scoped editorial briefs created from reviewed growth recommendations.
CREATE TABLE IF NOT EXISTS website_content_briefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES workspace_projects(id) ON DELETE CASCADE,
    report_id UUID NOT NULL REFERENCES website_audit_reports(id) ON DELETE CASCADE,
    action_id TEXT NOT NULL CHECK (length(trim(action_id)) BETWEEN 1 AND 160),
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 300),
    brief TEXT NOT NULL CHECK (length(trim(brief)) BETWEEN 1 AND 10000),
    target_keyword TEXT NOT NULL DEFAULT '' CHECK (length(target_keyword) <= 300),
    evidence_url TEXT NOT NULL DEFAULT '' CHECK (length(evidence_url) <= 2048),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','in_review','approved','rejected')),
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    reviewed_by UUID REFERENCES app_users(id) ON DELETE RESTRICT,
    review_note TEXT CHECK (review_note IS NULL OR length(review_note) <= 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    UNIQUE (workspace_id, report_id, action_id),
    FOREIGN KEY (project_id, workspace_id)
        REFERENCES workspace_projects(id, workspace_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS website_content_briefs_workspace_status_idx
    ON website_content_briefs(workspace_id, status, updated_at DESC);
