-- Scope recorded WhatsApp opt-in evidence to the business account it covers.
-- Existing opt-ins remain readable but fail closed until reconfirmed for an account.
ALTER TABLE outreach_contact_controls
    ADD COLUMN IF NOT EXISTS whatsapp_account_id UUID
    REFERENCES workspace_whatsapp_accounts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS outreach_contact_controls_whatsapp_account_idx
    ON outreach_contact_controls(workspace_id, whatsapp_account_id)
    WHERE whatsapp_opt_in_at IS NOT NULL;
