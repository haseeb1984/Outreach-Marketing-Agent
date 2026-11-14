# Durable website-growth worker operations

The API stores one-off and recurring website-growth scans in PostgreSQL. A separate, continuously running worker is required to execute queued scans; the API and dashboard do not execute queue jobs themselves.

## Run locally or on a dedicated worker host

From `backend/`, install `requirements.txt`, configure the same trusted `DATABASE_URL` and required encryption/secret settings as the backend, and apply migrations through `039_website_audit_job_idempotency.sql` for the current durable growth worker. The scheduler also requires migrations 035 and 036.

Run one scheduling/processing pass:

```sh
python scripts/run_workspace_growth_worker.py --once
```

Run continuously under a process supervisor:

```sh
python scripts/run_workspace_growth_worker.py --poll-seconds 3
```

Keep the worker on a persistent process host. Do not run it as a serverless HTTP request or expose it as a public endpoint. Use a supervisor to restart a crashed process and collect stdout/stderr in the platform log service. Use a dedicated database role with only the permissions needed by the application schema; never put credentials in command-line arguments or commit environment files.

## Safety and behavior

- Claims jobs with PostgreSQL row locks and expiring leases; separate worker instances may safely compete for work.
- Revalidates the workspace's verified domain immediately before fetching; uses bounded pages, depth, redirects, response bytes, and timeouts.
- Stores results in the owning workspace's audit history and records only stable, sanitized error codes in queue state.
- Recurring schedules enqueue idempotent jobs and reserve usage through the existing subscription store.
- This worker only runs read-only website growth scans. It does not send email or WhatsApp messages.
- A successful archive/code merge is not evidence of operational readiness. Before launch, verify a worker is continuously supervised, create a test job, observe a terminal status and saved report, exercise retry/lease recovery, and confirm logs/alerts are available.

## Current limitation

This is the first executable worker for the website-growth queue, not a general-purpose worker for SMTP delivery or WhatsApp outbound delivery. Those provider workflows remain separately gated.


## Production-like host deployment

For a hardened systemd unit, secret-file permissions, migration prerequisites, restart behavior, and the release acceptance checklist, follow [Growth Worker Host Runbook](GROWTH_WORKER_HOST_RUNBOOK.md). The runbook is operational guidance only; it does not imply a host has been provisioned or a production scan has passed.
