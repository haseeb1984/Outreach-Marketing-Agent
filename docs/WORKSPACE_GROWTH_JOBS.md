# Workspace website-growth jobs

The website-growth scan API queues bounded, read-only research jobs. It does not send outreach or publish changes.

## Prerequisites

1. Apply the repository migrations, including `002_workspace_jobs.sql`, and confirm the database readiness endpoint returns `200`.
2. Configure `DATABASE_URL`, `SECRET_KEY`, and the public HTTPS origin.
3. Sign in with a verified account and create/select a workspace.
4. Verify the website domain for that same workspace through the domain-verification workflow.
5. Run a worker process from the backend directory:

   ```sh
   python -m app.workers.website_growth_worker
   ```

The worker is a separate long-running process. Deploying the API alone does not execute queued jobs. Run the worker under a process supervisor and monitor its logs/restarts before enabling this feature for customers.

## Queue a scan

Send an authenticated, CSRF-protected request:

```http
POST /api/v1/workspace-jobs/website-growth-scan
Content-Type: application/json
X-CSRF-Token: <session csrf token>
Idempotency-Key: workspace-project-scan-2026-10-28
Cookie: <authenticated session cookie>
```

```json
{
  "workspace_id": "workspace-id-from-the-authenticated-workspace-list",
  "start_url": "https://verified.example.com/",
  "business_type": "B2B SaaS",
  "target_market": "United States",
  "target_queries": ["workflow automation", "CRM integration"],
  "max_pages": 10,
  "max_depth": 2
}
```

The server requires membership in the requested workspace and verifies the URL against that workspace's persisted domain authorization. The queue stores a normalized HTTPS URL without query strings or fragments. Optional idempotency keys are scoped to workspace and job type. Reusing a key returns the existing job rather than inserting a duplicate.

## Read job status

Use `GET /api/v1/workspace-jobs?workspace_id=<workspace-id>&limit=25&offset=0`. This requires at least viewer membership and returns only job metadata for that workspace; it does not expose stored payloads or research results through this listing endpoint.

Statuses are `queued`, `running`, `succeeded`, `failed`, and `cancelled`. A queue record being created means only that the work was accepted. A worker must claim and finish it before the scan is complete. A scan may fail if the site cannot be safely reached or the worker/database is unavailable.

## Operational limits

- Each scan is limited to 10 pages and depth 2.
- The queue uses PostgreSQL persistence, idempotency keys, bounded attempts, leases and stale-worker fencing.
- Do not put secrets, credentials, session tokens or private data in job payloads.
- The endpoint does not enable email or WhatsApp sending. Outreach remains a separate, human-approved workflow.
- Before production launch, verify worker supervision, migration execution, tenant-isolation tests, backups and restore, and real-domain browser acceptance.
