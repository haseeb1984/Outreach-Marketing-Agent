-- WhatsApp inbox ownership, lifecycle and auditable internal collaboration.
ALTER TABLE whatsapp_conversations
    ADD COLUMN IF NOT EXISTS assigned_to_user_id TEXT,
    ADD COLUMN IF NOT EXISTS inbox_status TEXT NOT NULL DEFAULT 'open',
    ADD COLUMN IF NOT EXISTS priority TEXT NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ,
    ADD CONSTRAINT whatsapp_conversations_inbox_status_check
      CHECK (inbox_status IN ('open','pending','resolved')),
    ADD CONSTRAINT whatsapp_conversations_priority_check
      CHECK (priority IN ('low','normal','high','urgent'));

CREATE INDEX IF NOT EXISTS whatsapp_conversations_workspace_inbox_idx
    ON whatsapp_conversations(workspace_id,inbox_status,priority,updated_at DESC);

CREATE INDEX IF NOT EXISTS whatsapp_conversations_assignee_idx
    ON whatsapp_conversations(workspace_id,assigned_to_user_id,inbox_status);

CREATE TABLE IF NOT EXISTS whatsapp_conversation_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    conversation_id UUID NOT NULL,
    author_user_id TEXT NOT NULL,
    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 5000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT whatsapp_conversation_notes_conversation_fk
      FOREIGN KEY (conversation_id) REFERENCES whatsapp_conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS whatsapp_conversation_notes_timeline_idx
    ON whatsapp_conversation_notes(workspace_id,conversation_id,created_at DESC,id DESC);
