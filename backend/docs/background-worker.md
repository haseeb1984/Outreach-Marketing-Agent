# Background worker operations

The website-growth worker is a separate process; the API does not start it automatically.

## Prerequisites
- Configure `DATABASE_URL` using a secret manager/environment variable.
- Apply database migrations explicitly from the `backend` directory with `python -m app.db.migrations`.
- Provision a real workspace before enqueuing jobs. Do not expose queue operations publicly until server-side authentication and workspace membership authorization exist.
- Verify that the database schema is current, including `workspace_jobs`.

## Run
From the `backend` directory, install `requirements.txt` and run:

```bash
python -m app.workers.website_growth_worker
```

The worker polls PostgreSQL, claims one eligible job at a time, and maintains a bounded 5-minute lease. It accepts only `website_growth_scan` jobs and HTTPS start URLs. Scan limits are capped at 10 pages and depth 2. Results are saved to the job row for later retrieval by a future authenticated API.

## Safety boundaries
- Workspace ID comes from the claimed database row, never from the job payload.
- The pipeline loads verified domains from the workspace-scoped database store before fetching a website.
- Jobs never send email or WhatsApp messages and never modify client websites.
- Error records use controlled codes rather than raw exception text.
- The fetch layer performs DNS/public-IP checks and bounded redirects, but a separate DNS lookup does not eliminate DNS rebinding. Production multi-tenant deployment still needs an egress proxy that pins the validated destination IP to the actual connection.
- There is not yet an account/session authentication system or public enqueue/status API. Do not expose queue operations publicly until workspace membership authorization, quotas, audit logging, and egress controls are implemented and tested.
