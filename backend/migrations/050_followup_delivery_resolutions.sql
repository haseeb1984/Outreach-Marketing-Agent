-- Auditable admin resolution of failed or uncertain follow-up delivery outcomes.
CREATE TABLE IF NOT EXISTS outreach_followup_delivery_resolutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    enrollment_id UUID NOT NULL REFERENCES outreach_followup_enrollments(id) ON DELETE RESTRICT,
    draft_id UUID NOT NULL REFERENCES outreach_drafts(id) ON DELETE RESTRICT,
    delivery_id UUID NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('email','whatsapp')),
    outcome TEXT NOT NULL CHECK (outcome IN ('delivered','not_delivered')),
    provider_status TEXT,
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 12 AND 2000),
    evidence_url TEXT NOT NULL CHECK (evidence_url LIKE 'https://%'),
    resolved_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outreach_followup_delivery_resolutions_enrollment_idx
    ON outreach_followup_delivery_resolutions(workspace_id,enrollment_id,resolved_at DESC);
