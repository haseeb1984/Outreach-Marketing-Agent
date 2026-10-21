-- Idempotent inbound reply inbox. Raw provider payloads and credentials are never persisted.
CREATE TABLE IF NOT EXISTS outreach_conversation_messages (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 prospect_id UUID NOT NULL REFERENCES crm_prospects(id) ON DELETE CASCADE,
 provider TEXT NOT NULL CHECK(length(trim(provider)) BETWEEN 1 AND 80),
 provider_event_id TEXT NOT NULL CHECK(length(trim(provider_event_id)) BETWEEN 1 AND 300),
 provider_message_id TEXT NOT NULL CHECK(length(trim(provider_message_id)) BETWEEN 1 AND 500),
 in_reply_to_provider_message_id TEXT CHECK(in_reply_to_provider_message_id IS NULL OR length(in_reply_to_provider_message_id)<=500),
 channel TEXT NOT NULL CHECK(channel IN ('email','whatsapp')),
 direction TEXT NOT NULL DEFAULT 'inbound' CHECK(direction='inbound'),
 body TEXT NOT NULL CHECK(length(trim(body)) BETWEEN 1 AND 10000),
 occurred_at TIMESTAMPTZ NOT NULL,
 received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(provider,provider_event_id)
);
CREATE INDEX IF NOT EXISTS outreach_conversation_workspace_prospect_idx
 ON outreach_conversation_messages(workspace_id,prospect_id,occurred_at DESC,id);
