-- Persist the exact catalog package selected by a verified subscription event.
-- Existing rows remain NULL and are resolved by entitlement matching for display only.
ALTER TABLE workspace_subscriptions
    ADD COLUMN IF NOT EXISTS plan_slug text;

CREATE INDEX IF NOT EXISTS workspace_subscriptions_plan_slug_idx
    ON workspace_subscriptions (plan_slug);
