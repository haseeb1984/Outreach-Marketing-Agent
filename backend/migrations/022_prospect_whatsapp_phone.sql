-- Optional E.164 phone field for workspace-scoped WhatsApp reply matching.
ALTER TABLE crm_prospects
    ADD COLUMN IF NOT EXISTS contact_phone_e164 TEXT;
ALTER TABLE crm_prospects
    DROP CONSTRAINT IF EXISTS crm_prospects_contact_phone_e164_format;
ALTER TABLE crm_prospects
    ADD CONSTRAINT crm_prospects_contact_phone_e164_format
    CHECK (contact_phone_e164 IS NULL OR contact_phone_e164 ~ '^[+][1-9][0-9]{7,14}$');
CREATE UNIQUE INDEX IF NOT EXISTS crm_prospects_workspace_phone_unique
    ON crm_prospects (workspace_id, contact_phone_e164)
    WHERE archived_at IS NULL AND contact_phone_e164 IS NOT NULL;
