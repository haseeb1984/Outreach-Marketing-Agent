# Supervised growth-worker host setup

This runbook deploys the **durable audit-report worker** in `backend/scripts/run_workspace_growth_worker.py`. It is separate from the FastAPI process and must run on a persistent host with network access to PostgreSQL and the approved outbound web-fetch path.

## Host prerequisites

- A dedicated Linux VM/container host with systemd (the service file is not for Vercel serverless functions).
- A dedicated unprivileged `oma-worker` account and group.
- A checked-out release at `/opt/outreach-marketing-agent`, Python virtual environment at `/opt/outreach-marketing-agent/venv`, and backend dependencies installed.
- The worker host's egress policy must enforce the same production SSRF controls as the API. DNS pre-resolution alone does not eliminate DNS-rebinding races; use a trusted egress proxy that pins validated IPs.
- A database role with only required application-schema permissions. Do not use a superuser role for the worker.

## Configure secrets safely

Create `/etc/outreach-marketing-agent/worker.env` as root, owned by root and readable only by the worker group (for example mode `0640`). Set `DATABASE_URL` and any required application configuration there. Never commit this file, paste values into tickets, or put secrets in the unit file or process arguments.

The service uses a fixed working directory and virtualenv path. If your host layout differs, update the unit before enabling it. Keep application releases immutable during a running job; deploy by stopping the service, switching the release, then starting it again.

## Install and start

1. Copy `ops/systemd/outreach-growth-worker.service` to `/etc/systemd/system/outreach-growth-worker.service`.
2. Confirm `/etc/outreach-marketing-agent/worker.env` exists with restrictive permissions and the worker can read it.
3. From the release's `backend/` directory, install dependencies and apply reviewed migrations using the project's migration process. Do not auto-run migrations from worker startup.
4. Verify the deployed schema includes migrations through `039_website_audit_job_idempotency.sql` and the worker account can access the required tables. Migration 039 adds the audit-report job linkage used by the current worker; migrations 035 and 036 establish the growth schedules and quota status.
5. Run a one-shot smoke test as the service account: `sudo -u oma-worker /opt/outreach-marketing-agent/venv/bin/python /opt/outreach-marketing-agent/backend/scripts/run_workspace_growth_worker.py --once`.
6. Install and start the service:
   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable --now outreach-growth-worker
   sudo systemctl status outreach-growth-worker
   ```
7. Inspect sanitized service output with `journalctl -u outreach-growth-worker -n 100 --no-pager`.

## Release acceptance checklist

- [ ] Apply migrations on the intended database and record the migration ledger.
- [ ] Verify service restart after a controlled process exit.
- [ ] Enqueue one test scan for a verified domain; observe a terminal job state and a corresponding `website_audit_reports` row in the same workspace.
- [ ] Verify a cancelled/inactive subscription prevents a queued scan from starting.
- [ ] Verify an invalid payload fails with a stable error code and no network fetch.
- [ ] Exercise lease expiry/reclaim in staging and confirm the stale worker cannot complete the job.
- [ ] Confirm logs/alerts detect repeated scheduler errors, worker restarts and a growing queue.
- [ ] Run backup checksum verification and a restore rehearsal against a separate recovery database.
- [ ] Confirm provider credentials, live email delivery, WhatsApp sending and Paddle live billing are independently staged and explicitly approved.

## Important boundaries

The unit makes the process restartable; it does not prove a successful production deployment or a real scan. A one-shot run may simply find no eligible jobs. The release is not launch-ready until the acceptance checklist is executed against the actual production-like environment. This worker handles website-growth scans only; it does not deliver queued email or WhatsApp outreach.

## Additional supervised processes

The durable scan worker, recurring schedule dispatcher, approval-only follow-up scheduler and WhatsApp sender are separate processes. A running API or scan worker does not imply that recurring schedules, follow-ups or outbound deliveries are being processed. Install and verify only the processes required by the enabled product features.

### Recurring growth scheduler

1. Create `/etc/outreach-marketing-agent/scheduler.env` as root-owned and readable only by the service group (for example mode `0640`). Set the production `DATABASE_URL` and required application settings; never place secret values in the unit file.
2. Install `ops/systemd/outreach-growth-scheduler.service` as `/etc/systemd/system/outreach-growth-scheduler.service`.
3. Confirm the database has migrations 035 and 036 and run the scheduler smoke tests in CI before enabling it.
4. Enable with: `sudo systemctl daemon-reload && sudo systemctl enable --now outreach-growth-scheduler`.
5. Verify `systemctl status outreach-growth-scheduler` and inspect sanitized logs with `journalctl -u outreach-growth-scheduler -n 100 --no-pager`. Confirm a due schedule advances and its idempotent job is visible in the same workspace.

### Approval-only campaign follow-up scheduler

This is a separate long-running process from the growth scheduler. It materializes due follow-up steps as drafts; it does **not** send email or WhatsApp messages. Human approval and the normal delivery policy remain required.

1. Reuse the restricted `/etc/outreach-marketing-agent/scheduler.env` file only if it contains the correct database and application settings for this release; otherwise create a separate root-owned, group-readable environment file and update the unit's `EnvironmentFile` path.
2. Install `ops/systemd/outreach-campaign-followup-worker.service` as `/etc/systemd/system/outreach-campaign-followup-worker.service`.
3. Confirm the follow-up schema migrations are applied on the intended database. Do not run migrations from the worker.
4. Enable with: `sudo systemctl daemon-reload && sudo systemctl enable --now outreach-campaign-followup-worker`.
5. Verify `systemctl status outreach-campaign-followup-worker` and `journalctl -u outreach-campaign-followup-worker -n 100 --no-pager`. In a controlled test workspace, confirm a due step creates an approval-pending draft and does not create a provider delivery or send.

### WhatsApp dispatch worker

This worker is deliberately fail-closed and must remain disabled until Meta sandbox acceptance, approved-template/consent checks, production credentials, and quota reconciliation have been reviewed.

1. Create `/etc/outreach-marketing-agent/whatsapp-worker.env` with restrictive permissions and required application settings. Configure both `WHATSAPP_DISPATCH_ENABLED=true` and the application setting `whatsapp_dispatch_enabled=true` only after acceptance; the process requires both configuration paths to opt in. Do not copy production credentials into tickets or logs.
2. Install `ops/systemd/outreach-whatsapp-dispatch-worker.service` as `/etc/systemd/system/outreach-whatsapp-dispatch-worker.service`.
3. Before enabling, verify migration 038, active Meta credentials, webhook/status reconciliation, recipient consent and template policy, and explicit product-owner approval for outbound sends.
4. Enable only after the above gates pass: `sudo systemctl daemon-reload && sudo systemctl enable --now outreach-whatsapp-dispatch-worker`.
5. Verify the service status and sanitized logs. Test a controlled approved recipient and confirm provider status, queue state, and quota reservation reconcile. If acceptance has not passed, leave this service disabled; its startup is expected to fail closed.

### Five-minute delivery automation workflow

`.github/workflows/process-due-deliveries.yml` is a separate GitHub Actions scheduled workflow, not a systemd worker. It runs every five minutes and calls the protected backend endpoints for due email deliveries, verified WhatsApp inbox events, approval-only follow-up draft materialization and the WhatsApp outbound queue endpoint. The outbound endpoint remains subject to its server-side feature gates.

1. Configure repository secrets `BACKEND_BASE_URL` and `CRON_SECRET`; the workflow rejects a non-HTTPS backend URL and a cron secret shorter than 32 bytes.
2. Use the workflow's manual dispatch for a controlled verification only after confirming the target environment and endpoint side effects.
3. Verify each named task reports success in the run summary; the workflow fails overall if any task fails, even though each task is allowed to complete independently.
4. Confirm the backend logs and persisted queue/draft states match the workflow response. A green scheduled run alone does not prove that every queued item was eligible or processed.
5. Historical GitHub runner-allocation failures are an infrastructure concern; if a scheduled run never allocates a runner, no endpoint task has executed. Alert on missing scheduled runs as well as failed task outcomes.

Do not treat installing these unit files or configuring GitHub secrets as proof that services have been deployed, enabled or accepted on a persistent host. Production acceptance still requires the relevant checklists above to be executed and evidenced.
