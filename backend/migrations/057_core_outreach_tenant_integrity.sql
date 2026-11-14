-- Enforce tenant alignment for the core campaign, draft and delivery graph.
-- Existing single-column foreign keys remain to preserve established delete behavior.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM outreach_drafts d
    LEFT JOIN outreach_campaigns c ON c.id=d.campaign_id
    LEFT JOIN crm_prospects p ON p.id=d.prospect_id
    WHERE c.id IS NULL OR p.id IS NULL
       OR c.workspace_id <> d.workspace_id
       OR p.workspace_id <> d.workspace_id
  ) THEN
    RAISE EXCEPTION 'outreach_draft_workspace_relationship_mismatch';
  END IF;

  IF EXISTS (
    SELECT 1 FROM outreach_deliveries d
    LEFT JOIN outreach_drafts dr ON dr.id=d.draft_id
    LEFT JOIN workspace_email_accounts a ON a.id=d.email_account_id
    WHERE dr.id IS NULL OR dr.workspace_id <> d.workspace_id
       OR (d.email_account_id IS NOT NULL
           AND (a.id IS NULL OR a.workspace_id <> d.workspace_id))
  ) THEN
    RAISE EXCEPTION 'outreach_delivery_workspace_relationship_mismatch';
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS outreach_campaigns_id_workspace_uidx
  ON outreach_campaigns(id,workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS outreach_drafts_id_workspace_uidx
  ON outreach_drafts(id,workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS workspace_email_accounts_id_workspace_uidx
  ON workspace_email_accounts(id,workspace_id);

ALTER TABLE outreach_drafts
  ADD CONSTRAINT outreach_drafts_campaign_workspace_fk
    FOREIGN KEY (campaign_id,workspace_id)
    REFERENCES outreach_campaigns(id,workspace_id) ON DELETE CASCADE,
  ADD CONSTRAINT outreach_drafts_prospect_workspace_fk
    FOREIGN KEY (prospect_id,workspace_id)
    REFERENCES crm_prospects(id,workspace_id);

ALTER TABLE outreach_deliveries
  ADD CONSTRAINT outreach_deliveries_draft_workspace_fk
    FOREIGN KEY (draft_id,workspace_id)
    REFERENCES outreach_drafts(id,workspace_id) ON DELETE RESTRICT,
  ADD CONSTRAINT outreach_deliveries_email_account_workspace_fk
    FOREIGN KEY (email_account_id,workspace_id)
    REFERENCES workspace_email_accounts(id,workspace_id);
