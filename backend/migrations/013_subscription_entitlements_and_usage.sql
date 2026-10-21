-- Server-owned subscription snapshots and atomic feature quota reservations.
-- Billing provider events must be verified before updating workspace_subscriptions.
CREATE TABLE IF NOT EXISTS workspace_subscriptions (
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (length(provider) BETWEEN 1 AND 40),
    provider_customer_id TEXT,
    provider_subscription_id TEXT UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('active','trialing','past_due','cancelled','incomplete','unpaid','paused')),
    billing_period_starts_at TIMESTAMPTZ NOT NULL,
    billing_period_ends_at TIMESTAMPTZ NOT NULL,
    entitlements JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(entitlements) = 'object'),
    provider_event_created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (billing_period_ends_at > billing_period_starts_at)
);
CREATE INDEX IF NOT EXISTS idx_workspace_subscriptions_status_period
    ON workspace_subscriptions(status, billing_period_ends_at);

CREATE TABLE IF NOT EXISTS feature_usage_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    feature TEXT NOT NULL CHECK (length(feature) BETWEEN 1 AND 100),
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 8 AND 200),
    billing_period_starts_at TIMESTAMPTZ NOT NULL,
    billing_period_ends_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved','consumed','released')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, idempotency_key),
    CHECK (billing_period_ends_at > billing_period_starts_at)
);
CREATE INDEX IF NOT EXISTS idx_feature_usage_active_period
    ON feature_usage_reservations(workspace_id, feature, billing_period_starts_at, billing_period_ends_at)
    WHERE status IN ('reserved','consumed');
