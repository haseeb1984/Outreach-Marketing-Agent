-- Append-only audit timeline for WhatsApp inbox collaboration actions.
CREATE TABLE IF NOT EXISTS whatsapp_conversation_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    conversation_id UUID NOT NULL,
    actor_user_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
      event_type IN ('assignment_changed','status_changed','priority_changed','note_added','note_deleted')
    ),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT whatsapp_conversation_activity_conversation_fk
      FOREIGN KEY (conversation_id) REFERENCES whatsapp_conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS whatsapp_conversation_activity_timeline_idx
    ON whatsapp_conversation_activity(workspace_id,conversation_id,created_at DESC,id DESC);

CREATE INDEX IF NOT EXISTS whatsapp_conversation_activity_actor_idx
    ON whatsapp_conversation_activity(workspace_id,actor_user_id,created_at DESC);
