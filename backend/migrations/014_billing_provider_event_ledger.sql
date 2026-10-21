-- Idempotent ledger for verified billing-provider lifecycle events.
-- Store identifiers and outcome only; never persist raw provider payloads or secrets.
CREATE TABLE IF NOT EXISTS billing_provider_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 40),
    provider_event_id TEXT NOT NULL CHECK (length(trim(provider_event_id)) BETWEEN 1 AND 300),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider_subscription_id TEXT NOT NULL CHECK (length(trim(provider_subscription_id)) BETWEEN 1 AND 300),
    event_created_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    outcome TEXT NOT NULL CHECK (outcome IN ('applied','stale')),
    UNIQUE(provider, provider_event_id)
);
CREATE INDEX IF NOT EXISTS idx_billing_provider_events_workspace_time
    ON billing_provider_events(workspace_id, event_created_at DESC);
