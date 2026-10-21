-- Persist channel suppression and evidence-backed WhatsApp opt-in.
CREATE TABLE IF NOT EXISTS outreach_contact_controls (
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 prospect_id UUID NOT NULL REFERENCES crm_prospects(id) ON DELETE CASCADE,
 email_suppressed BOOLEAN NOT NULL DEFAULT FALSE,
 whatsapp_opt_in_at TIMESTAMPTZ,
 whatsapp_opt_in_evidence_url TEXT CHECK (whatsapp_opt_in_evidence_url IS NULL OR (length(whatsapp_opt_in_evidence_url) <= 2048 AND whatsapp_opt_in_evidence_url ~* '^https://')),
 updated_by UUID NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY (workspace_id,prospect_id),
 CHECK ((whatsapp_opt_in_at IS NULL AND whatsapp_opt_in_evidence_url IS NULL) OR (whatsapp_opt_in_at IS NOT NULL AND whatsapp_opt_in_evidence_url IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS outreach_contact_controls_suppression_idx ON outreach_contact_controls(workspace_id,prospect_id) WHERE email_suppressed;
