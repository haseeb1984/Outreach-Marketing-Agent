-- Durable, tenant-scoped background work queue.
-- Job payloads must contain only validated inputs; never store secrets or raw auth tokens.
CREATE TABLE IF NOT EXISTS workspace_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (job_type IN ('website_growth_scan')),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    payload JSONB NOT NULL,
    result JSONB,
    error_code TEXT,
    idempotency_key TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
    run_after TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_by TEXT,
    locked_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    CONSTRAINT workspace_jobs_idempotency_key_length
        CHECK (idempotency_key IS NULL OR length(idempotency_key) BETWEEN 1 AND 200),
    CONSTRAINT workspace_jobs_lease_state CHECK (
        (status = 'running' AND locked_by IS NOT NULL AND locked_at IS NOT NULL
         AND lease_expires_at IS NOT NULL)
        OR (status <> 'running' AND locked_by IS NULL AND locked_at IS NULL
            AND lease_expires_at IS NULL)
    ),
    CONSTRAINT workspace_jobs_finished_state CHECK (
        (status IN ('succeeded', 'failed', 'cancelled') AND finished_at IS NOT NULL)
        OR (status IN ('queued', 'running') AND finished_at IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_jobs_idempotency
    ON workspace_jobs (workspace_id, job_type, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_workspace_jobs_claim
    ON workspace_jobs (run_after, created_at)
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_workspace_jobs_expired_leases
    ON workspace_jobs (lease_expires_at)
    WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_workspace_jobs_workspace_recent
    ON workspace_jobs (workspace_id, created_at DESC);
