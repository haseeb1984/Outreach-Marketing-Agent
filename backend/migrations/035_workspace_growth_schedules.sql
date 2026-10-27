-- Durable, tenant-scoped recurring website-growth scan schedules.
-- Schedules enqueue read-only research jobs; they never send outreach.
CREATE TABLE IF NOT EXISTS workspace_growth_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL DEFAULT 'website_growth_scan'
        CHECK (job_type = 'website_growth_scan'),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    interval_hours INTEGER NOT NULL CHECK (interval_hours BETWEEN 6 AND 720),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused')),
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_enqueued_at TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_workspace_growth_schedules_due
    ON workspace_growth_schedules(next_run_at, created_at)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_workspace_growth_schedules_workspace
    ON workspace_growth_schedules(workspace_id, created_at DESC);
