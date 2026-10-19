-- Authentication, workspace membership, revocable sessions, and audit foundation.
-- No public auth endpoint should use these tables until email delivery, rate limits,
-- CSRF/session policy, and route-level authorization have been implemented and tested.
CREATE TABLE IF NOT EXISTS app_users (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL,
 email_verified_at TIMESTAMPTZ,
 status TEXT NOT NULL DEFAULT 'pending_verification' CHECK (status IN ('pending_verification','active','suspended','deleted')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 last_login_at TIMESTAMPTZ,
 CONSTRAINT app_users_email_normalized CHECK (email=lower(email) AND email=trim(email) AND length(email) BETWEEN 3 AND 320),
 CONSTRAINT app_users_password_hash_nonempty CHECK (length(password_hash) BETWEEN 1 AND 512)
);
CREATE TABLE IF NOT EXISTS workspace_memberships (
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK (role IN ('owner','admin','member','viewer')),
 status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','revoked')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY (workspace_id,user_id)
);
CREATE INDEX IF NOT EXISTS idx_workspace_memberships_user_active ON workspace_memberships(user_id,workspace_id) WHERE status='active';
CREATE TABLE IF NOT EXISTS auth_sessions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 token_sha256 CHAR(64) NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 expires_at TIMESTAMPTZ NOT NULL,
 last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 revoked_at TIMESTAMPTZ,
 user_agent TEXT,
 CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_active ON auth_sessions(user_id,expires_at) WHERE revoked_at IS NULL;
CREATE TABLE IF NOT EXISTS email_verification_tokens (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 token_sha256 CHAR(64) NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 expires_at TIMESTAMPTZ NOT NULL,
 consumed_at TIMESTAMPTZ,
 CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_email_verification_user_pending ON email_verification_tokens(user_id,expires_at) WHERE consumed_at IS NULL;
CREATE TABLE IF NOT EXISTS password_reset_tokens (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 token_sha256 CHAR(64) NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 expires_at TIMESTAMPTZ NOT NULL,
 consumed_at TIMESTAMPTZ,
 CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_password_reset_user_pending ON password_reset_tokens(user_id,expires_at) WHERE consumed_at IS NULL;
CREATE TABLE IF NOT EXISTS security_audit_events (
 id BIGSERIAL PRIMARY KEY,
 workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
 actor_user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
 event_type TEXT NOT NULL CHECK (length(event_type) BETWEEN 1 AND 100),
 outcome TEXT NOT NULL CHECK (outcome IN ('success','denied','failure')),
 request_id TEXT,
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CHECK (jsonb_typeof(metadata)='object')
);
CREATE INDEX IF NOT EXISTS idx_security_audit_workspace_recent ON security_audit_events(workspace_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_audit_actor_recent ON security_audit_events(actor_user_id,created_at DESC);
