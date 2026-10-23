-- Platform-admin-managed billing catalog. Provider price IDs remain server-side.
CREATE TABLE IF NOT EXISTS platform_billing_plans (
    slug text PRIMARY KEY CHECK (slug ~ '^[a-z0-9][a-z0-9_-]{0,79}$'),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
    description text NOT NULL DEFAULT '' CHECK (length(description) <= 500),
    price_id text NOT NULL CHECK (price_id ~ '^pri_[A-Za-z0-9_-]+$'),
    display_price text,
    currency text,
    billing_interval text,
    entitlements jsonb NOT NULL CHECK (jsonb_typeof(entitlements) = 'object'),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS platform_billing_plans_active_idx ON platform_billing_plans (active, name);
