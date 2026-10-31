-- Personal, workspace-scoped WhatsApp inbox filter presets.
CREATE TABLE IF NOT EXISTS whatsapp_inbox_saved_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
    filters JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(filters)='object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS whatsapp_inbox_saved_views_name_idx
    ON whatsapp_inbox_saved_views(workspace_id,user_id,lower(name));
CREATE INDEX IF NOT EXISTS whatsapp_inbox_saved_views_owner_idx
    ON whatsapp_inbox_saved_views(workspace_id,user_id,updated_at DESC);
