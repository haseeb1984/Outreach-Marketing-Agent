# Launch preflight

Run this before a release from the repository root:

```bash
cd backend
python -m scripts.launch_preflight
```

The command emits one JSON document and exits non-zero when required configuration or
operational artifacts are missing. Save the JSON output as a release artifact, but remove
any operator-added private metadata before sharing it outside the deployment team. It checks the PostgreSQL DSN shape, session-secret
length, provider-encryption key, HTTPS origins, SMTP all-or-none configuration, Paddle
mode consistency, Meta configuration completeness/version format, migration artifacts,
backup tooling, and growth-worker supervision/runbook.

## What this does not prove

Warnings are intentional. A green local preflight is not evidence that a remote deploy
is running the latest commit, migrations have been applied to production, SMTP/Paddle/
WhatsApp credentials work, or a backup can be restored. Verify those independently
using the deployed health endpoint, database migration ledger, provider sandbox
transactions, and an isolated restore drill. Never put secret values in release reports.

## CI

Tests live in `backend/tests/test_launch_preflight.py` and exercise valid configuration,
secret validation, URL restrictions, partial provider configuration, billing-mode
consistency, missing operational artifacts, and the distinction between local checks
and remote acceptance.
