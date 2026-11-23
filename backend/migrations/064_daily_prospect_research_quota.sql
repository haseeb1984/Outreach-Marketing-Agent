-- Daily prospect-research usage is independent of the subscription billing cycle.
-- The existing prospect_research monthly_limit value is reused as the daily cap.
CREATE TABLE IF NOT EXISTS daily_feature_usage_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    feature TEXT NOT NULL CHECK (feature = 'prospect_research'),
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 8 AND 200),
    usage_date DATE NOT NULL,
    units INTEGER NOT NULL DEFAULT 1 CHECK (units >= 0),
    status TEXT NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved','consumed','released')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_daily_feature_usage_workspace_day
    ON daily_feature_usage_reservations(workspace_id, feature, usage_date)
    WHERE status IN ('reserved','consumed');

ALTER TABLE daily_feature_usage_reservations
    ADD COLUMN IF NOT EXISTS units INTEGER NOT NULL DEFAULT 1 CHECK (units >= 0);
