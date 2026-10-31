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
- Scheduler: `POST /api/v1/follow-up-sequences/process-due` with `Authorization: Bearer $CRON_SECRET`

Each sequence has 1–10 steps. Step 1's delay is measured from enrollment; later step delays are measured from the previous confirmed delivery. Delays are 0–43,200 minutes. Supported plain-text substitutions are `{{first_name}}`, `{{company}}`, `{{business}}` and `{{offer}}`.

**Safety model:** the due scheduler only creates a new `pending_approval` draft. It never sends a follow-up. A workspace admin must approve the draft and separately queue it through the channel's normal delivery path. Email suppression, WhatsApp account-scoped opt-in, WhatsApp opt-out, prospect reply/disqualification/conversion, archived contacts, campaign state and sequence state are checked before materializing each step. Sending a step advances the enrollment only after a confirmed provider outcome. Failed or uncertain delivery pauses the enrollment for operator review. Rejected drafts stop the enrollment. Paused sequences block dispatch of their already-created follow-up drafts.

## Supervised follow-up worker

For a continuously running host, install `ops/systemd/outreach-campaign-followup-worker.service` alongside the backend workers. It uses the same protected `/etc/outreach-marketing-agent/scheduler.env` file as the growth scheduler and requires `DATABASE_URL`. After installing the release and applying migration 049:

```sh
sudo install -o root -g root -m 0644 ops/systemd/outreach-campaign-followup-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now outreach-campaign-followup-worker
sudo systemctl status outreach-campaign-followup-worker
```

The service only materializes pending-approval drafts. It cannot send email or WhatsApp. Existing email due-delivery and WhatsApp dispatch workers remain separately configured and gated. Alternatively, a trusted external scheduler can call `POST /api/v1/follow-up-sequences/process-due` with the scheduler bearer secret. Do not expose the scheduler secret to the browser. WhatsApp dispatch remains independently controlled by its existing explicit feature flag and Meta activation requirements.
