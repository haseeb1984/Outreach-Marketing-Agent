-- Database-backed, fixed-window throttling buckets for authentication and sensitive actions.
-- Store only keyed digests, never raw email addresses, IP addresses, tokens, or credentials.
CREATE TABLE IF NOT EXISTS auth_rate_limit_buckets (
 key_digest CHAR(64) PRIMARY KEY CHECK (key_digest ~ '^[0-9a-f]{64}$'),
 window_started_at TIMESTAMPTZ NOT NULL,
 attempts INTEGER NOT NULL CHECK (attempts >= 1),
 updated_at TIMESTAMPTZ NOT NULL,
 CHECK (updated_at >= window_started_at)
);
CREATE INDEX IF NOT EXISTS idx_auth_rate_limit_updated ON auth_rate_limit_buckets(updated_at);
