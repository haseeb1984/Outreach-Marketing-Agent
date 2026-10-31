-- Persist Paddle's current transaction.past_due state in the sanitized invoice ledger.
ALTER TABLE billing_transactions
    DROP CONSTRAINT IF EXISTS billing_transactions_status_check;

ALTER TABLE billing_transactions
    ADD CONSTRAINT billing_transactions_status_check
    CHECK (status IN ('completed', 'payment_failed', 'past_due'));
