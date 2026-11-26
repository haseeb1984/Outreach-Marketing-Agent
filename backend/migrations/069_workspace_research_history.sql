-- Persist public prospect and creator research evidence within its workspace.
CREATE TABLE IF NOT EXISTS workspace_research_runs (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 research_type TEXT NOT NULL CHECK (research_type IN ('prospects','influencers')),
 query TEXT NOT NULL CHECK (length(query) BETWEEN 3 AND 400),
 provider TEXT NOT NULL CHECK (provider IN ('brave_search','serpapi')),
 parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
 results JSONB NOT NULL DEFAULT '[]'::jsonb,
 result_count INTEGER NOT NULL DEFAULT 0 CHECK (result_count >= 0 AND result_count <= 20),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS workspace_research_runs_history_idx ON workspace_research_runs(workspace_id, created_at DESC, id);
