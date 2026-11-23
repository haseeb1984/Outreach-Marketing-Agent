-- Preserve prior Paddle Price IDs so existing subscriptions continue to map to
-- their package after checkout moves to a newly-created recurring Price.
CREATE TABLE IF NOT EXISTS platform_billing_plan_price_history (
    price_id text PRIMARY KEY CHECK (price_id ~ '^pri_[A-Za-z0-9_-]+$'),
    plan_slug text NOT NULL REFERENCES platform_billing_plans(slug) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS platform_billing_plan_price_history_slug_idx
    ON platform_billing_plan_price_history (plan_slug, created_at DESC);
