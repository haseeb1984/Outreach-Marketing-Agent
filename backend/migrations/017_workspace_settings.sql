-- Workspace display names for customer-facing workspace settings.
ALTER TABLE workspaces
    ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT 'Workspace'
    CHECK (length(trim(name)) BETWEEN 1 AND 160);
