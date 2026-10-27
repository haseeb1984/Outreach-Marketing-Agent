-- Workspace-scoped delivery records must not block deletion of a workspace and its
-- dependent drafts/prospects/accounts. The workspace is the tenant boundary; deleting
-- that tenant should cascade through its delivery records as well.
ALTER TABLE outreach_deliveries
    DROP CONSTRAINT IF EXISTS outreach_deliveries_draft_id_fkey;
ALTER TABLE outreach_deliveries
    ADD CONSTRAINT outreach_deliveries_draft_id_fkey
    FOREIGN KEY (draft_id) REFERENCES outreach_drafts(id) ON DELETE CASCADE;

ALTER TABLE whatsapp_outbound_deliveries
    DROP CONSTRAINT IF EXISTS whatsapp_outbound_deliveries_account_id_fkey;
ALTER TABLE whatsapp_outbound_deliveries
    ADD CONSTRAINT whatsapp_outbound_deliveries_account_id_fkey
    FOREIGN KEY (account_id) REFERENCES workspace_whatsapp_accounts(id) ON DELETE CASCADE;

ALTER TABLE whatsapp_outbound_deliveries
    DROP CONSTRAINT IF EXISTS whatsapp_outbound_deliveries_draft_id_fkey;
ALTER TABLE whatsapp_outbound_deliveries
    ADD CONSTRAINT whatsapp_outbound_deliveries_draft_id_fkey
    FOREIGN KEY (draft_id) REFERENCES outreach_drafts(id) ON DELETE CASCADE;

ALTER TABLE whatsapp_outbound_deliveries
    DROP CONSTRAINT IF EXISTS whatsapp_outbound_deliveries_prospect_id_fkey;
ALTER TABLE whatsapp_outbound_deliveries
    ADD CONSTRAINT whatsapp_outbound_deliveries_prospect_id_fkey
    FOREIGN KEY (prospect_id) REFERENCES crm_prospects(id) ON DELETE CASCADE;

ALTER TABLE whatsapp_outbound_deliveries
    DROP CONSTRAINT IF EXISTS whatsapp_outbound_deliveries_usage_reservation_id_fkey;
ALTER TABLE whatsapp_outbound_deliveries
    ADD CONSTRAINT whatsapp_outbound_deliveries_usage_reservation_id_fkey
    FOREIGN KEY (usage_reservation_id) REFERENCES feature_usage_reservations(id) ON DELETE CASCADE;
