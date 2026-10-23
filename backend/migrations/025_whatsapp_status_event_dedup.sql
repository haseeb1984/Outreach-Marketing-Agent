-- PostgreSQL UNIQUE constraints treat NULL timestamps as distinct, so duplicate
-- provider status webhooks without timestamps could previously be stored repeatedly.
WITH ranked AS (
    SELECT ctid,
           row_number() OVER (
               PARTITION BY provider_message_id, status,
                            COALESCE(provider_timestamp, 'epoch'::timestamptz)
               ORDER BY received_at, id
           ) AS duplicate_number
    FROM whatsapp_delivery_status_events
)
DELETE FROM whatsapp_delivery_status_events AS events
USING ranked
WHERE events.ctid = ranked.ctid
  AND ranked.duplicate_number > 1;

CREATE UNIQUE INDEX IF NOT EXISTS whatsapp_delivery_status_dedup_idx
    ON whatsapp_delivery_status_events (
        provider_message_id,
        status,
        (COALESCE(provider_timestamp, 'epoch'::timestamptz))
    );

