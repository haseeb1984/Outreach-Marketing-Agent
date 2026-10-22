-- Expiring, one-use workspace invitations with hashed bearer tokens.
CREATE TABLE IF NOT EXISTS workspace_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    invited_email TEXT NOT NULL CHECK (invited_email=lower(invited_email) AND invited_email=trim(invited_email) AND length(invited_email) BETWEEN 3 AND 320),
    role TEXT NOT NULL CHECK (role IN ('admin','member','viewer')),
    token_sha256 CHAR(64) NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','revoked','expired')),
    invited_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > created_at),
    CHECK ((status='accepted' AND accepted_at IS NOT NULL) OR status<>'accepted'),
    CHECK ((status='revoked' AND revoked_at IS NOT NULL) OR status<>'revoked')
);
CREATE INDEX IF NOT EXISTS workspace_invitations_workspace_recent_idx
    ON workspace_invitations (workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS workspace_invitations_pending_email_idx
    ON workspace_invitations (workspace_id, invited_email, expires_at)
    WHERE status='pending';
