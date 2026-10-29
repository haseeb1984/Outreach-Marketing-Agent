# Background worker operations

The durable website-growth queue is processed by **one canonical worker entry point**: `backend/scripts/run_workspace_growth_worker.py`. The API and dashboard enqueue/read jobs; they do not execute queue jobs themselves.

## Run

From the `backend/` directory, install `requirements.txt`, configure the same trusted `DATABASE_URL` and required application settings as the backend, and run a single smoke pass:

```sh
python scripts/run_workspace_growth_worker.py --once
```

For continuous operation on a persistent host, use a process supervisor and run:

```sh
python scripts/run_workspace_growth_worker.py --poll-seconds 3
```

The maintained systemd unit is `ops/systemd/outreach-growth-worker.service`; the full host setup and release acceptance procedure is in [Growth Worker Host Runbook](../../docs/GROWTH_WORKER_HOST_RUNBOOK.md).

## Canonical worker and legacy module

Do **not** start `python -m app.workers.website_growth_worker` as a second production consumer. That older module is retained for compatibility/tests; the canonical script validates usage reservations, writes completed reports to `website_audit_reports`, and records the report ID on the durable job. Running a different entry point can produce inconsistent result persistence and complicate operational diagnosis.

## Safety boundaries

- Workspace identity comes from the claimed database row, never from caller-controlled job payload.
- The worker revalidates the workspace's verified domain and subscription/usage reservation before fetching.
- Fetching is bounded by page/depth/redirect/response/time limits. DNS pre-resolution alone does not eliminate DNS rebinding; production egress must pin validated destinations through a trusted egress proxy.
- The worker performs read-only website-growth scans only. It never sends email or WhatsApp messages and never modifies customer websites.
- Queue failures use stable sanitized error codes; provider credentials must not be placed in source control, command arguments, or logs.
- A successful code merge or a one-shot run that finds no jobs is not operational acceptance. Follow the host runbook to verify supervised execution, a test job and saved report, subscription denial, retry/lease recovery, logs/alerts, and backup/restore readiness.
- Do not re-run migrations merely to start a worker. Confirm the intended database's migration ledger/schema against the reviewed release before enabling a service.
