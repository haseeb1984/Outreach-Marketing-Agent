-- Persist evidence-linked outreach drafts and explicit human review decisions.
CREATE TABLE IF NOT EXISTS workspace_outreach_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    channel TEXT NOT NULL CHECK (channel IN ('email', 'whatsapp')),
    client_business TEXT NOT NULL CHECK (length(trim(client_business)) BETWEEN 1 AND 200),
    client_offer TEXT NOT NULL CHECK (length(trim(client_offer)) BETWEEN 1 AND 500),
    prospect_name TEXT NOT NULL CHECK (length(trim(prospect_name)) BETWEEN 1 AND 200),
    prospect_evidence_url TEXT NOT NULL CHECK (length(trim(prospect_evidence_url)) BETWEEN 1 AND 2048),
    verified_relevance TEXT NOT NULL CHECK (length(trim(verified_relevance)) BETWEEN 1 AND 1000),
    verified_facts JSONB NOT NULL CHECK (jsonb_typeof(verified_facts) = 'array'),
    call_to_action TEXT NOT NULL CHECK (length(trim(call_to_action)) BETWEEN 1 AND 300),
    subject TEXT CHECK (subject IS NULL OR length(subject) <= 300),
    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 10000),
    whatsapp_opt_in_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'draft_requires_human_review'
        CHECK (status IN ('draft_requires_human_review', 'approved', 'rejected')),
    reviewed_by UUID REFERENCES app_users(id) ON DELETE SET NULL,
    review_note TEXT CHECK (review_note IS NULL OR length(review_note) <= 1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    CHECK (
        (status = 'draft_requires_human_review' AND reviewed_by IS NULL AND reviewed_at IS NULL)
        OR (status IN ('approved', 'rejected') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
    ),
    CHECK (channel <> 'whatsapp' OR whatsapp_opt_in_confirmed = TRUE)
);
CREATE INDEX IF NOT EXISTS workspace_outreach_drafts_recent_idx
    ON workspace_outreach_drafts (workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS workspace_outreach_drafts_review_idx
    ON workspace_outreach_drafts (workspace_id, status, created_at DESC);
