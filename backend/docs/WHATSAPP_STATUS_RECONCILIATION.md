# WhatsApp delivery-status reconciliation

The Meta webhook inbox and event processor persist status callbacks, but a callback can
arrive before the dispatch worker commits the provider message ID to the outbound queue.
In that race the event is stored while the immediate queue update finds no matching row.

Run `python -m scripts.reconcile_whatsapp_delivery_statuses` from `backend/` as a
trusted scheduled task after webhook processing. It replays persisted status events in
bounded batches, matches by workspace, WhatsApp account, and provider message ID, and
updates only matching outbound records. It never sends messages.

The reconciler keeps status progression monotonic: a late sent callback cannot regress a
delivered/read state, and a failed callback cannot overwrite a confirmed delivered/read
state. Run it periodically; use the JSON counters for basic monitoring. Production
scheduling, database migration application, and Meta live callback acceptance still need
environment-specific verification before enabling outbound dispatch.
