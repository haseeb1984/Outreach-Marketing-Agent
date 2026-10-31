-- Human-approved, timed follow-up sequences. Automation creates review drafts only; it never sends them.
CREATE TABLE IF NOT EXISTS outreach_followup_sequences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL REFERENCES outreach_campaigns(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
    channel TEXT NOT NULL CHECK (channel IN ('email','whatsapp')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','paused','archived')),
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, workspace_id)
);
CREATE INDEX IF NOT EXISTS outreach_followup_sequences_campaign_idx
    ON outreach_followup_sequences (workspace_id, campaign_id, status);

CREATE TABLE IF NOT EXISTS outreach_followup_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence_id UUID NOT NULL REFERENCES outreach_followup_sequences(id) ON DELETE CASCADE,
    step_number SMALLINT NOT NULL CHECK (step_number BETWEEN 1 AND 10),
    delay_minutes INTEGER NOT NULL CHECK (delay_minutes BETWEEN 0 AND 43200),
    subject_template TEXT CHECK (subject_template IS NULL OR length(subject_template) <= 300),
    body_template TEXT NOT NULL CHECK (length(trim(body_template)) BETWEEN 1 AND 10000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sequence_id, step_number)
);
CREATE INDEX IF NOT EXISTS outreach_followup_steps_order_idx
    ON outreach_followup_steps (sequence_id, step_number);

CREATE TABLE IF NOT EXISTS outreach_followup_enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    sequence_id UUID NOT NULL REFERENCES outreach_followup_sequences(id) ON DELETE CASCADE,
    prospect_id UUID NOT NULL REFERENCES crm_prospects(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
    current_step SMALLINT NOT NULL DEFAULT 1 CHECK (current_step BETWEEN 1 AND 11),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
      'active','awaiting_approval','paused','completed','stopped_replied',
      'stopped_opt_out','stopped_ineligible','stopped_rejected','archived'
    )),
    next_run_at TIMESTAMPTZ,
    paused_next_run_at TIMESTAMPTZ,
    current_draft_id UUID REFERENCES outreach_drafts(id) ON DELETE SET NULL,
    last_delivery_id UUID REFERENCES outreach_deliveries(id) ON DELETE SET NULL,
    last_whatsapp_delivery_id UUID REFERENCES whatsapp_outbound_deliveries(id) ON DELETE SET NULL,
    last_error_code TEXT CHECK (last_error_code IS NULL OR length(last_error_code) <= 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sequence_id, prospect_id)
);
CREATE INDEX IF NOT EXISTS outreach_followup_enrollments_due_idx
    ON outreach_followup_enrollments (next_run_at, id)
    WHERE status='active';
CREATE UNIQUE INDEX IF NOT EXISTS outreach_followup_enrollments_draft_idx
    ON outreach_followup_enrollments (current_draft_id)
    WHERE current_draft_id IS NOT NULL;
