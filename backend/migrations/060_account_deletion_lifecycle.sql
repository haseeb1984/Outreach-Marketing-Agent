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

-- Database-level guard against a stale session creating a fresh membership after
-- account deletion. Writers lock the workspace first; this trigger then locks the
-- account row, matching the deletion and membership lifecycle lock order.
CREATE OR REPLACE FUNCTION reject_deleted_account_workspace_membership()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    account_status TEXT;
BEGIN
    IF NEW.status = 'revoked' THEN
        RETURN NEW;
    END IF;
    SELECT status INTO account_status
    FROM app_users
    WHERE id = NEW.user_id
    FOR UPDATE;
    IF account_status IS NULL OR account_status = 'deleted' THEN
        RAISE EXCEPTION 'deleted_account_membership_forbidden'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS workspace_memberships_reject_deleted_account
    ON workspace_memberships;
CREATE TRIGGER workspace_memberships_reject_deleted_account
    BEFORE INSERT OR UPDATE OF user_id, status ON workspace_memberships
    FOR EACH ROW EXECUTE FUNCTION reject_deleted_account_workspace_membership();

-- Pending invitations cannot be recreated by a deleted account. Revocation remains
-- allowed so account deletion can clean up existing pending invitations atomically.
CREATE OR REPLACE FUNCTION reject_deleted_account_pending_invitation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    account_status TEXT;
BEGIN
    IF NEW.status <> 'pending' THEN
        RETURN NEW;
    END IF;
    SELECT status INTO account_status
    FROM app_users
    WHERE id = NEW.invited_by
    FOR UPDATE;
    IF account_status IS NULL OR account_status = 'deleted' THEN
        RAISE EXCEPTION 'deleted_account_invitation_forbidden'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS workspace_invitations_reject_deleted_account
    ON workspace_invitations;
CREATE TRIGGER workspace_invitations_reject_deleted_account
    BEFORE INSERT OR UPDATE OF invited_by, status ON workspace_invitations
    FOR EACH ROW EXECUTE FUNCTION reject_deleted_account_pending_invitation();
