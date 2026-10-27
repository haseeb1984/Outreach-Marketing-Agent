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
4. Verify the deployed schema includes migrations through `036_growth_schedule_quota_status.sql` and the worker account can access the required tables.
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
