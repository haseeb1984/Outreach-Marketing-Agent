-- Treat ambiguous SMTP/network outcomes separately from definite failures.
-- This state is deliberately terminal for the send endpoint to prevent duplicate outreach.
ALTER TABLE outreach_deliveries DROP CONSTRAINT IF EXISTS outreach_deliveries_status_check;
ALTER TABLE outreach_deliveries
 ADD CONSTRAINT outreach_deliveries_status_check
 CHECK(status IN ('queued','processing','sent','failed','cancelled','uncertain'));
