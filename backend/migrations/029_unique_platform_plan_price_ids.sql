-- One Paddle price must map to exactly one package for deterministic webhook reconciliation.
CREATE UNIQUE INDEX IF NOT EXISTS platform_billing_plans_price_id_unique
    ON platform_billing_plans (price_id);
