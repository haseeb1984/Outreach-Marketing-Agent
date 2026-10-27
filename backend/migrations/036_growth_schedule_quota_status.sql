-- Make recurring schedule quota skips visible and auditable.
ALTER TABLE workspace_growth_schedules
    ADD COLUMN IF NOT EXISTS last_attempted_at TIMESTAMPTZ;
ALTER TABLE workspace_growth_schedules
    ADD COLUMN IF NOT EXISTS last_error_code TEXT
        CHECK (last_error_code IS NULL OR length(last_error_code) <= 100);
