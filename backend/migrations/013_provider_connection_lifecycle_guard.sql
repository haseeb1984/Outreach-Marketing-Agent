-- Enforce provider connection lifecycle invariants in PostgreSQL, including writes
-- that bypass the application API. This migration intentionally does not implement OAuth.
CREATE OR REPLACE FUNCTION enforce_workspace_provider_connection_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = OLD.status THEN
        -- Keep the connected-state proof intact even if a later UPDATE changes metadata only.
        IF NEW.status = 'connected' AND (
            NEW.provider_account_id IS NULL
            OR length(btrim(NEW.provider_account_id)) = 0
            OR NEW.secret_reference IS NULL
            OR length(btrim(NEW.secret_reference)) = 0
            OR cardinality(NEW.granted_scopes) = 0
            OR NEW.last_validated_at IS NULL
        ) THEN
            RAISE EXCEPTION 'connected provider connection requires validated account metadata'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.status = 'revoked' THEN
            NEW.revoked_at := COALESCE(NEW.revoked_at, OLD.revoked_at, now());
        END IF;
        RETURN NEW;
    END IF;

    -- Revoked is terminal: reconnecting must create a fresh authorization record.
    IF OLD.status = 'revoked' THEN
        RAISE EXCEPTION 'revoked provider connections are terminal'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status = 'connected' THEN
        IF OLD.status NOT IN ('pending', 'error') THEN
            RAISE EXCEPTION 'invalid provider connection transition to connected'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.provider_account_id IS NULL
           OR length(btrim(NEW.provider_account_id)) = 0
           OR NEW.secret_reference IS NULL
           OR length(btrim(NEW.secret_reference)) = 0
           OR cardinality(NEW.granted_scopes) = 0
           OR NEW.last_validated_at IS NULL THEN
            RAISE EXCEPTION 'connected provider connection requires validated account metadata'
                USING ERRCODE = 'check_violation';
        END IF;
        NEW.revoked_at := NULL;
        NEW.last_error_code := NULL;
    ELSIF NEW.status = 'error' THEN
        IF OLD.status NOT IN ('pending', 'connected') THEN
            RAISE EXCEPTION 'invalid provider connection transition to error'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.last_error_code IS NULL OR length(btrim(NEW.last_error_code)) = 0 THEN
            RAISE EXCEPTION 'provider connection error requires a stable error code'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.status = 'revoked' THEN
        NEW.revoked_at := COALESCE(NEW.revoked_at, now());
    ELSE
        RAISE EXCEPTION 'invalid provider connection status transition'
            USING ERRCODE = 'check_violation';
    END IF;

    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS workspace_provider_connection_transition_guard
    ON workspace_provider_connections;

CREATE TRIGGER workspace_provider_connection_transition_guard
BEFORE UPDATE ON workspace_provider_connections
FOR EACH ROW
EXECUTE FUNCTION enforce_workspace_provider_connection_transition();
