-- Record the account deletion timestamp separately from ordinary profile updates.
-- Existing soft-deleted accounts receive their historical last-update timestamp.
ALTER TABLE app_users
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

UPDATE app_users
SET deleted_at = COALESCE(deleted_at, updated_at, created_at, now())
WHERE status = 'deleted' AND deleted_at IS NULL;

ALTER TABLE app_users
    DROP CONSTRAINT IF EXISTS app_users_deleted_at_status_consistency;

ALTER TABLE app_users
    ADD CONSTRAINT app_users_deleted_at_status_consistency
    CHECK (
        (status = 'deleted' AND deleted_at IS NOT NULL)
        OR (status <> 'deleted' AND deleted_at IS NULL)
    );

CREATE INDEX IF NOT EXISTS app_users_deleted_at_idx
    ON app_users (deleted_at)
    WHERE status = 'deleted';
