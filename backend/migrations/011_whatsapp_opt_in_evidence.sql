-- Record auditable WhatsApp opt-in evidence on a workspace-local prospect.
ALTER TABLE workspace_prospects
  ADD COLUMN IF NOT EXISTS whatsapp_opt_in_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS whatsapp_opt_in_source TEXT,
  ADD COLUMN IF NOT EXISTS whatsapp_opt_in_evidence_url TEXT;

ALTER TABLE workspace_prospects
  DROP CONSTRAINT IF EXISTS workspace_prospects_whatsapp_opt_in_evidence_check;
ALTER TABLE workspace_prospects
  ADD CONSTRAINT workspace_prospects_whatsapp_opt_in_evidence_check
  CHECK (
    (whatsapp_opt_in_at IS NULL AND whatsapp_opt_in_source IS NULL AND whatsapp_opt_in_evidence_url IS NULL)
    OR
    (whatsapp_opt_in_at IS NOT NULL
      AND whatsapp_opt_in_source IS NOT NULL AND length(btrim(whatsapp_opt_in_source)) BETWEEN 1 AND 200
      AND whatsapp_opt_in_evidence_url IS NOT NULL
      AND whatsapp_opt_in_evidence_url ~ '^https://[^[:space:]]+$')
  );
