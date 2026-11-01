# Production operations and launch runbook

This document is the operator procedure for the agreed deployment topology:

- **Frontend:** Hostinger Business (Next.js application).
- **API:** existing FastAPI deployment at `https://outreach-marketing-agent.vercel.app`.
- **Database:** managed PostgreSQL/Neon; API and workers connect server-side only.
- **Persistent workers:** a Linux/systemd host for growth scheduling, growth scans, campaign follow-ups, and (only after explicit approval) WhatsApp dispatch.
- **Billing:** Paddle hosted checkout and signed webhooks.

A checked-in configuration, successful Git commit, or CI workflow is not proof that a production service is deployed or healthy. Record live evidence in the release record before declaring launch readiness.

## 1. Production change and release control

1. Release only a reviewed commit on `main`; record its full SHA and the previous known-good SHA.
2. Confirm the frontend and API are being released from the intended repository paths and the intended deployment targets. Do not deploy the frontend to Vercel: Hostinger is the agreed frontend host.
3. Review changed migrations and provider behavior. Back up PostgreSQL before any production schema change.
4. Apply migrations through the explicitly approved Neon migration workflow. Do not run migrations automatically from API or worker startup.
5. Confirm API liveness and database readiness, then deploy/restart persistent workers, then publish the Hostinger frontend artifact.
6. Run the smoke checklist below and record timestamp, deployed SHAs, HTTP status, migration ledger, worker state, and operator.
7. If acceptance fails, stop risky workers first, roll back application code to the recorded previous release, and preserve logs/evidence. Do not assume a code rollback reverses a database migration.

### Required release record

Record the following in the operator's private release log (never commit secrets):

- Release ID, date/time UTC, operator, source commit SHA.
- API deployment ID/URL and deployed commit; frontend artifact checksum and Hostinger release identifier.
- Database identity (non-secret host/database label), applied migration versions, backup filename and SHA-256.
- systemd unit versions and active states.
- Results for public health, readiness, login, dashboard, billing sandbox, email, WhatsApp (if enabled), and rollback decision.
- Outstanding warnings, incident link, and approval for any live sending or live billing.

## 2. Host and service supervision

Use a dedicated Linux host, unprivileged service accounts, immutable release directories, and root-owned environment files. Do not run workers inside the web request process or rely on an ephemeral serverless filesystem.

Install the service files from `ops/systemd/` into `/etc/systemd/system/`. The checked-in units assume:

- Release directory: `/opt/outreach-marketing-agent`.
- Python environment: `/opt/outreach-marketing-agent/venv`.
- Service account: `oma-worker` (backup service uses `oma-backup`).
- Environment directory: `/etc/outreach-marketing-agent/`.
- Backup storage: a separately provisioned, encrypted and access-controlled mount at `/mnt/oma-backups`.

Create service users/groups and directories before enabling units. Restrict environment files (for example root:oma-worker mode 0640, backup.env root:oma-backup mode 0640). Set `DATABASE_URL` in each relevant file and only the settings required by that process. Never put secrets in unit files, shell history, deployment logs, or Git.

The independently supervised processes are:

| Unit | Purpose | Enablement policy |
|---|---|---|
| `outreach-growth-worker.service` | Executes durable website growth jobs | Required for growth scans |
| `outreach-growth-scheduler.service` | Enqueues recurring growth scans | Required for recurring scans |
| `outreach-campaign-followup-worker.service` | Processes eligible, approval-gated follow-up steps | Required for follow-up automation |
| `outreach-whatsapp-dispatch-worker.service` | Dispatches approved WhatsApp queue entries | Keep disabled until Meta/provider, consent, template, quota and product-owner gates pass |
| `outreach-database-backup.timer` | Starts periodic PostgreSQL backup service | Required after encrypted backup mount is provisioned |

Install and inspect:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now outreach-growth-worker outreach-growth-scheduler outreach-campaign-followup-worker
sudo systemctl status outreach-growth-worker outreach-growth-scheduler outreach-campaign-followup-worker
sudo journalctl -u outreach-growth-worker -u outreach-growth-scheduler -u outreach-campaign-followup-worker -n 100 --no-pager
```

Do not enable WhatsApp dispatch merely because its unit exists. The process requires explicit opt-in and must remain stopped until its separate acceptance and approval gates have passed.

## 3. PostgreSQL backups and recovery

The backup helper is `backend/scripts/database_backup.py`. It creates a PostgreSQL custom-format dump, writes a SHA-256 sidecar, uses restrictive file permissions, and suppresses connection details from command output. It requires PostgreSQL client tools (`pg_dump`, `pg_restore`).

### Configure scheduled backups

Provision `/mnt/oma-backups` as a durable encrypted volume or securely mounted off-host backup target. The systemd service intentionally refuses to run unless that mount is present; do not replace it with an ordinary local directory.

Create `/etc/outreach-marketing-agent/backup.env`:

```sh
DATABASE_URL=postgresql://...
BACKUP_DIR=/mnt/oma-backups
```

The actual URL belongs only in the protected host environment file. Set ownership/permissions for the `oma-backup` account, then install and enable:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now outreach-database-backup.timer
sudo systemctl list-timers outreach-database-backup.timer
sudo systemctl start outreach-database-backup.service
sudo systemctl status outreach-database-backup.service
```

The timer is configured for every six hours with persistent catch-up after host downtime. Monitor for failed runs, low disk space, missing mount, and missing checksum sidecars. Copy/replicate backups to a separate failure domain and enforce an operator-approved retention policy on the storage system; the application helper does not implement remote replication or automatic retention deletion.

### Verify and restore

```sh
cd /opt/outreach-marketing-agent/backend
/opt/outreach-marketing-agent/venv/bin/python scripts/database_backup.py verify /mnt/oma-backups/<backup-file>.dump
```

For a restore rehearsal, provision a new, empty, isolated recovery database. Configure `SOURCE_DATABASE_URL` to identify the production source and `RESTORE_DATABASE_URL` to identify the distinct recovery target; then explicitly set `CONFIRM_RESTORE=YES` and run:

```sh
CONFIRM_RESTORE=YES /opt/outreach-marketing-agent/venv/bin/python scripts/database_backup.py restore /mnt/oma-backups/<backup-file>.dump
```

The restore helper rejects the same source and target database identity and does not use `pg_restore --clean`. Never point it at the live production database. After restore, run the read-only schema diagnostic and application smoke checks against the recovery target. Record measured restore duration and recovered data timestamp.

**Initial operational targets (must be accepted by the owner):** backup interval/RPO target 6 hours; recovery-time objective (RTO) target 4 hours. These are proposed targets, not measured guarantees. A real restore rehearsal is required before treating either as achieved.

## 4. Health, readiness and monitoring

- `GET /health` is a liveness check only; HTTP 200 does not prove PostgreSQL or migrations are ready.
- `GET /ready` checks PostgreSQL connectivity and required schema/migration state. Treat non-200 as a release/traffic gate.
- Run `python -m scripts.diagnose_database_readiness` from `backend/` for a read-only check of every local migration file and ledger entry, required tables/columns, and the WhatsApp tenant-isolation foreign keys and unique indexes. It must not be used as a migration command.
- Run `python -m scripts.launch_preflight --require-launch-ready` from the repository root for local release-artifact/configuration checks. It intentionally reports remote deployment, provider acceptance, applied migrations, and restore rehearsal as warnings until those facts are independently verified.

Configure external uptime monitoring against `/health` and `/ready` from outside the hosting network. Alert on:
- Liveness/readiness failures or sustained latency.
- API 5xx/error-rate increases and repeated database connection failures.
- Worker service inactive/restarting, non-zero process exits, or growing oldest-job age/queue depth.
- Repeated webhook failures/dead-letter growth and unresolved uncertain deliveries.
- Backup timer missed/failed runs, absent checksum files, storage mount failure, and disk capacity thresholds.
- Paddle webhook processing failures and billing/subscription state reconciliation errors.

Send alerts to an actively monitored operator channel. Keep dashboards and logs free of credentials, authorization headers, session cookies, raw provider tokens, and full database URLs. Define a named on-call owner and escalation route before launch. The repository does not itself provision an external monitoring vendor or alert destination.

## 5. GitHub Actions scheduled dispatch

The repository workflow `.github/workflows/process-due-deliveries.yml` runs every five minutes and calls the authenticated API scheduler endpoints. Configure these repository Actions secrets before expecting scheduled processing:

- `BACKEND_BASE_URL`: HTTPS origin of the deployed FastAPI API, for example `https://outreach-marketing-agent.vercel.app`. Use the origin only; the workflow appends the API paths.
- `CRON_SECRET`: a high-entropy secret of at least 32 bytes. Configure the exact same value as the backend deployment's `CRON_SECRET` environment variable. Do not reuse the SMTP password, Paddle secret, Meta token, or application signing key.

In GitHub, open the repository **Settings → Secrets and variables → Actions → New repository secret** and add each secret by name. Secret values are write-only and must not be committed or pasted into logs. The workflow intentionally fails before dispatch if either value is missing, the URL is not HTTPS, or the cron secret is too short. After configuration, manually run the workflow once and confirm the email, WhatsApp inbox processing and WhatsApp queue task outcomes individually. A successful workflow dispatch is not proof that any eligible work existed; inspect sanitized API/worker outcomes. WhatsApp outbound dispatch must remain disabled until its separate consent, template, quota, provider and owner-approval gates pass.

## 6. Smoke acceptance checklist

Run after each production release and record evidence:

- [ ] Public frontend home, product, pricing, privacy, terms and contact pages return expected responses over HTTPS.
- [ ] API `/health` returns 200 and `/ready` returns 200 against the intended production database.
- [ ] Read-only database diagnostic reports all required migration versions, tables and columns present.
- [ ] Login, session refresh, logout, CSRF-protected mutation, workspace isolation and dashboard loading work on the real Hostinger origin.
- [ ] Email account diagnostics succeed; a controlled, explicitly approved test message is delivered and provider feedback is reconciled.
- [ ] Paddle sandbox checkout, signed webhook, subscription lifecycle, cancellation and entitlement/quota behavior are accepted before enabling live checkout.
- [ ] Meta webhook verification/signature, account mapping, documented opt-in/opt-out, approved templates, 24-hour policy, delivery status reconciliation and controlled recipient acceptance are complete before enabling WhatsApp dispatch.
- [ ] Growth scheduler and worker complete a verified-domain staging job; follow-up worker respects approval, pause, opt-out and channel eligibility.
- [ ] Backup is created, checksum/archive verified, copied to the separate failure domain, and restored into a fresh isolated database.
- [ ] External uptime/error/queue/backup alerts are delivered to the named on-call owner.
- [ ] Accessibility, responsive behavior, performance and crawl/indexing checks are accepted on the actual production frontend domain.

A missing result is **unverified**, not a pass.

## 6. Incident response and rollback

1. Declare incident severity, assign an incident lead, and record start time and affected services/workspaces.
2. For suspected unintended outreach, provider abuse, consent breach, or credential exposure: disable the relevant sender/credential first; stop the WhatsApp dispatch and campaign follow-up workers as appropriate. Preserve webhook and audit evidence.
3. For API/frontend regressions: capture deployment IDs and logs, compare against the last known-good release, and roll back application code through the relevant host's supported release mechanism.
4. For database incidents: stop writers before recovery. Do not blindly roll back SQL migrations. Prefer a reviewed forward fix; restore only into an isolated database first, validate it, and obtain explicit owner approval before any production cutover.
5. Rotate compromised provider credentials through their provider consoles, update protected environment settings, restart only affected services, and verify old credentials are revoked.
6. Reconcile queued, processing and uncertain deliveries carefully. Never automatically resend an ambiguous provider request; verify provider-side status first to avoid duplicate outreach.
7. Confirm readiness, worker state, queue age, provider webhook flow, backup health and customer-visible behavior before closing the incident.
8. Publish a concise post-incident review with timeline, impact, root cause, corrective actions, owner and due date.

## 7. External launch gates that source code cannot complete

These require authorized access to the actual production accounts and operator acceptance:

- Hostinger application upload/release, domain DNS/TLS, environment settings and real-origin browser acceptance.
- Vercel API production deployment identity, runtime health, logs and configured environment.
- Neon production migration ledger and database backup/restore rehearsal.
- Persistent host provisioning, systemd installation, worker enablement and monitoring destinations.
- SMTP live delivery acceptance, Paddle merchant/catalog/sandbox-to-live approval, and Meta business/app/phone-number/template approval.
- Legal review and publication of accurate privacy/terms/support details.
- Accessibility/performance acceptance and named incident/on-call ownership.

Do not mark the launch ready until the release record contains evidence for each applicable gate. Keep live Paddle checkout and WhatsApp dispatch disabled until their explicit acceptance gates pass.
