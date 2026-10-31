-- Enforce tenant alignment at the database boundary for WhatsApp inbox records.
-- Existing single-column FKs remain in place for their established delete semantics.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM whatsapp_conversations c
    LEFT JOIN workspace_whatsapp_accounts a ON a.id=c.account_id
    WHERE a.id IS NULL OR a.workspace_id <> c.workspace_id
  ) THEN
    RAISE EXCEPTION 'whatsapp_conversation_account_workspace_mismatch';
  END IF;
  IF EXISTS (
    SELECT 1 FROM whatsapp_conversations c
    JOIN crm_prospects p ON p.id=c.prospect_id
    WHERE p.workspace_id <> c.workspace_id
  ) THEN
    RAISE EXCEPTION 'whatsapp_conversation_prospect_workspace_mismatch';
  END IF;
  IF EXISTS (
    SELECT 1 FROM whatsapp_inbound_messages m
    JOIN whatsapp_conversations c ON c.id=m.conversation_id
    WHERE c.workspace_id <> m.workspace_id
  ) THEN
    RAISE EXCEPTION 'whatsapp_inbound_message_workspace_mismatch';
  END IF;
  IF EXISTS (
    SELECT 1 FROM whatsapp_conversation_notes n
    JOIN whatsapp_conversations c ON c.id=n.conversation_id
    WHERE c.workspace_id <> n.workspace_id
  ) THEN
    RAISE EXCEPTION 'whatsapp_conversation_note_workspace_mismatch';
  END IF;
  IF EXISTS (
    SELECT 1 FROM whatsapp_conversation_activity a
    JOIN whatsapp_conversations c ON c.id=a.conversation_id
    WHERE c.workspace_id <> a.workspace_id
  ) THEN
    RAISE EXCEPTION 'whatsapp_conversation_activity_workspace_mismatch';
  END IF;
  IF EXISTS (
    SELECT 1 FROM whatsapp_delivery_status_events e
    JOIN workspace_whatsapp_accounts a ON a.id=e.account_id
    WHERE a.workspace_id <> e.workspace_id
  ) THEN
    RAISE EXCEPTION 'whatsapp_delivery_status_workspace_mismatch';
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS workspace_whatsapp_accounts_id_workspace_uidx
  ON workspace_whatsapp_accounts(id,workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS crm_prospects_id_workspace_uidx
  ON crm_prospects(id,workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS whatsapp_conversations_id_workspace_uidx
  ON whatsapp_conversations(id,workspace_id);

ALTER TABLE whatsapp_conversations
  ADD CONSTRAINT whatsapp_conversations_account_workspace_fk
    FOREIGN KEY (account_id,workspace_id)
    REFERENCES workspace_whatsapp_accounts(id,workspace_id) ON DELETE CASCADE,
  ADD CONSTRAINT whatsapp_conversations_prospect_workspace_fk
    FOREIGN KEY (prospect_id,workspace_id)
    REFERENCES crm_prospects(id,workspace_id);

ALTER TABLE whatsapp_inbound_messages
  ADD CONSTRAINT whatsapp_inbound_messages_conversation_workspace_fk
    FOREIGN KEY (conversation_id,workspace_id)
    REFERENCES whatsapp_conversations(id,workspace_id) ON DELETE CASCADE;

ALTER TABLE whatsapp_conversation_notes
  ADD CONSTRAINT whatsapp_conversation_notes_workspace_fk
    FOREIGN KEY (conversation_id,workspace_id)
    REFERENCES whatsapp_conversations(id,workspace_id) ON DELETE CASCADE;

ALTER TABLE whatsapp_conversation_activity
  ADD CONSTRAINT whatsapp_conversation_activity_workspace_fk
    FOREIGN KEY (conversation_id,workspace_id)
    REFERENCES whatsapp_conversations(id,workspace_id) ON DELETE CASCADE;

ALTER TABLE whatsapp_delivery_status_events
  ADD CONSTRAINT whatsapp_delivery_status_events_account_workspace_fk
    FOREIGN KEY (account_id,workspace_id)
    REFERENCES workspace_whatsapp_accounts(id,workspace_id) ON DELETE CASCADE;
