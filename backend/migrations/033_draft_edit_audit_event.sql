-- Preserve an audit trail when a human edits draft content before approval.
ALTER TABLE outreach_draft_events
    DROP CONSTRAINT IF EXISTS outreach_draft_events_event_type_check;

ALTER TABLE outreach_draft_events
    ADD CONSTRAINT outreach_draft_events_event_type_check
    CHECK (event_type IN ('created','edited','approved','rejected'));
