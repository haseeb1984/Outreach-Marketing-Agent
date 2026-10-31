-- Track operator-controlled SLA pauses without losing elapsed-time accounting.
ALTER TABLE whatsapp_conversations
    ADD COLUMN IF NOT EXISTS sla_paused_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS sla_pause_reason TEXT,
    ADD COLUMN IF NOT EXISTS sla_paused_seconds INTEGER NOT NULL DEFAULT 0
      CHECK (sla_paused_seconds >= 0);

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='whatsapp_conversations'::regclass
          AND conname='whatsapp_conversations_sla_pause_reason_check'
    ) THEN
        ALTER TABLE whatsapp_conversations
            ADD CONSTRAINT whatsapp_conversations_sla_pause_reason_check
            CHECK (sla_pause_reason IS NULL OR length(sla_pause_reason) BETWEEN 1 AND 500);
    END IF;
END $migration$;

ALTER TABLE whatsapp_conversation_activity
    DROP CONSTRAINT IF EXISTS whatsapp_conversation_activity_event_type_check;
ALTER TABLE whatsapp_conversation_activity
    ADD CONSTRAINT whatsapp_conversation_activity_event_type_check
    CHECK (event_type IN (
      'assignment_changed','status_changed','priority_changed','note_added','note_deleted',
      'sla_paused','sla_resumed'
    ));

CREATE INDEX IF NOT EXISTS whatsapp_conversations_sla_paused_idx
    ON whatsapp_conversations(workspace_id,sla_paused_at)
    WHERE sla_paused_at IS NOT NULL;
