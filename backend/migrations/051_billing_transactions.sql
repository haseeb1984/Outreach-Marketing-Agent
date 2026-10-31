-- Sanitized Paddle transaction/invoice history, without raw webhook or payment data.
CREATE TABLE IF NOT EXISTS billing_transaction_events (
    provider text NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 40),
    provider_event_id text NOT NULL CHECK (length(trim(provider_event_id)) BETWEEN 1 AND 300),
    transaction_id text NOT NULL CHECK (length(trim(transaction_id)) BETWEEN 1 AND 120),
    event_created_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(provider, provider_event_id)
);
CREATE TABLE IF NOT EXISTS billing_transactions (
    provider text NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 40),
    transaction_id text NOT NULL CHECK (length(trim(transaction_id)) BETWEEN 1 AND 120),
    workspace_id text NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider_subscription_id text,
    invoice_number text,
    status text NOT NULL CHECK (status IN ('completed','payment_failed')),
    currency_code text CHECK (currency_code IS NULL OR length(currency_code)=3),
    total_minor numeric(20,0) CHECK (total_minor IS NULL OR total_minor >= 0),
    billed_at timestamptz NOT NULL,
    provider_event_created_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(provider, transaction_id)
);
CREATE INDEX IF NOT EXISTS billing_transactions_workspace_history_idx
    ON billing_transactions(workspace_id, billed_at DESC, transaction_id DESC);
