# Campaign scheduling and follow-up sequences

## Email scheduling

Approved email drafts can be queued with an optional timezone-aware `scheduled_at` ISO-8601 timestamp. Omit it or send null for immediate eligibility. The authenticated admin endpoints support rescheduling and cancellation while a delivery remains queued. The scheduler endpoint is:

- `POST /api/v1/deliveries/process-due`
- Authorization: `Bearer $CRON_SECRET` (minimum 32 UTF-8 bytes)
- Bounded batch: 1–100 deliveries

The endpoint rechecks campaign state, approval state, contact suppression, reply state, sender account state and usage entitlement before sending. Ambiguous SMTP outcomes become terminal `uncertain` records and are never blindly retried.

## Follow-up sequences

Migration `049_campaign_followup_sequences.sql` adds workspace-scoped sequences, ordered steps and prospect enrollments.

- Create: `POST /api/v1/campaigns/{campaign_id}/follow-up-sequences`
- List: `GET /api/v1/follow-up-sequences?workspace_id=...`
- Activate/pause/archive: `PATCH /api/v1/follow-up-sequences/{sequence_id}`
- Enroll a prospect: `POST /api/v1/follow-up-sequences/{sequence_id}/enroll`
- View enrollments: `GET /api/v1/follow-up-sequences/{sequence_id}/enrollments?workspace_id=...`
- Pause/resume/archive an enrollment: `PATCH /api/v1/follow-up-enrollments/{enrollment_id}`
- Resolve a failed/uncertain enrollment delivery after provider confirmation: `POST /api/v1/follow-up-enrollments/{enrollment_id}/resolve-delivery` (workspace admin; requires delivery ID, outcome, reason and HTTPS evidence URL).
- Scheduler: `POST /api/v1/follow-up-sequences/process-due` with `Authorization: Bearer $CRON_SECRET`

Each sequence has 1–10 steps. Step 1's delay is measured from enrollment; later step delays are measured from the previous confirmed delivery. Delays are 0–43,200 minutes. Supported plain-text substitutions are `{{first_name}}`, `{{company}}`, `{{business}}` and `{{offer}}`.

**Safety model:** the due scheduler only creates a new `pending_approval` draft. It never sends a follow-up. A workspace admin must approve the draft and separately queue it through the channel's normal delivery path. Email suppression, WhatsApp account-scoped opt-in, WhatsApp opt-out, prospect reply/disqualification/conversion, archived contacts, campaign state and sequence state are checked before materializing each step. Sending a step advances the enrollment only after a confirmed provider outcome. Failed or uncertain delivery pauses the enrollment for operator review. Rejected drafts stop the enrollment. Paused sequences block dispatch of their already-created follow-up drafts. A `pending_draft_conflict` pause can be resumed by a workspace admin only after the conflicting pending-approval draft has been resolved; the API refuses to resume while any matching pending draft remains. Delivery-failure and uncertain-outcome pauses are deliberately not resumable through the ordinary pause/resume control. The dedicated admin resolution endpoint accepts only the exact failed/uncertain delivery attached to the enrollment's current draft. Signed email provider `delivered` callbacks and authenticated Meta WhatsApp `delivered/read` status callbacks now advance the linked follow-up enrollment automatically and idempotently in the same transaction as the provider-state update. Email hard-bounce, spam-complaint and unsubscribe events immediately stop all active, awaiting-approval and paused email follow-up enrollments for that prospect; explicit unsubscribe endpoint does the same. Inbound WhatsApp STOP-family commands immediately stop all WhatsApp follow-up enrollments for the matched prospect and cancel queued WhatsApp sends with usage reservations released. Enrollment creation also rejects already-suppressed email contacts, WhatsApp opt-outs, disqualified and converted prospects. Uncertain and failed delivery pauses retain distinct reasons. Admin resolution remains the fallback for genuinely unresolved provider outcomes. A delivered resolution is accepted only when persisted provider feedback says email `delivered` or WhatsApp `delivered/read`; the enrollment advances exactly once inside the same database transaction and records actor, provider state, reason and evidence URL in a resolution ledger. A confirmed-not-delivered resolution stops the enrollment and never retries the old delivery. Unknown outcomes remain paused. Apply migration `050_followup_delivery_resolutions.sql` before using this endpoint.

## Supervised follow-up worker

For a continuously running host, install `ops/systemd/outreach-campaign-followup-worker.service` alongside the backend workers. It uses the same protected `/etc/outreach-marketing-agent/scheduler.env` file as the growth scheduler and requires `DATABASE_URL`. After installing the release and applying migrations 049 and 050:

```sh
sudo install -o root -g root -m 0644 ops/systemd/outreach-campaign-followup-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now outreach-campaign-followup-worker
sudo systemctl status outreach-campaign-followup-worker
```

The service only materializes pending-approval drafts. It cannot send email or WhatsApp. Existing email due-delivery and WhatsApp dispatch workers remain separately configured and gated. Alternatively, a trusted external scheduler can call `POST /api/v1/follow-up-sequences/process-due` with the scheduler bearer secret. The repository's `Process due campaign deliveries` GitHub Actions workflow also calls this endpoint every five minutes after validating `BACKEND_BASE_URL` and `CRON_SECRET`; its result is reported independently from email and WhatsApp tasks. This step only creates pending-approval drafts and does not approve or send them. Do not expose the scheduler secret to the browser. WhatsApp dispatch remains independently controlled by its existing explicit feature flag and Meta activation requirements.
