-- Auditable global admin actions; metadata must never include secrets or customer message bodies.
CREATE TABLE IF NOT EXISTS platform_admin_audit_events (
    id bigserial PRIMARY KEY,
    actor_user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    event_type text NOT NULL CHECK (length(event_type) BETWEEN 1 AND 120),
    target_type text NOT NULL CHECK (length(target_type) BETWEEN 1 AND 80),
    target_id text NOT NULL CHECK (length(target_id) BETWEEN 1 AND 200),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS platform_admin_audit_events_created_idx ON platform_admin_audit_events (created_at DESC);
CREATE INDEX IF NOT EXISTS platform_admin_audit_events_actor_idx ON platform_admin_audit_events (actor_user_id, created_at DESC);
