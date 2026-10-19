-- PostgreSQL schema proposal for persistent workspace domain verification.
-- Apply only after confirming the deployment database is PostgreSQL.
-- Never store raw DNS challenge tokens; persist only SHA-256 digests.

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workspace_domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    domain_ascii TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'verified', 'revoked')),
    verification_method TEXT NOT NULL CHECK (verification_method IN ('dns_txt')),
    verified_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT workspace_domains_normalized CHECK (
        domain_ascii = lower(domain_ascii) AND domain_ascii = trim(domain_ascii)
    ),
    UNIQUE (workspace_id, domain_ascii),
    CHECK (
        (status = 'pending' AND verified_at IS NULL AND revoked_at IS NULL)
        OR (status = 'verified' AND verified_at IS NOT NULL AND revoked_at IS NULL)
        OR (status = 'revoked' AND revoked_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_workspace_domains_active
    ON workspace_domains (workspace_id, domain_ascii)
    WHERE status = 'verified' AND revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS domain_verification_challenges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    domain_ascii TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method = 'dns_txt'),
    token_sha256 CHAR(64) NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'verified', 'expired', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,
    CONSTRAINT challenge_hash_hex CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (expires_at > created_at)
);

-- Verification implementation MUST perform these steps in one transaction:
-- 1. SELECT the challenge FOR UPDATE and validate workspace/domain/status/expiry.
-- 2. Query TXT records for exactly _oma-verify.<domain_ascii> via a trusted resolver.
-- 3. Compare the observed token's SHA-256 digest using constant-time comparison.
-- 4. UPDATE challenge status to verified and upsert workspace_domains status/verified_at.
-- 5. Commit; reject replay if challenge status is no longer pending.
-- DNS lookup is external and cannot be rolled back. Re-check challenge state under lock
-- after DNS returns before mutating persistent records.
-- The application must derive workspace_id from authenticated server-side identity,
-- never trust workspace_id or verified_domains supplied by an HTTP client.
