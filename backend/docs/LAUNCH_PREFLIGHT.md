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
backup tooling, all scheduler/growth/WhatsApp worker service units, and the worker runbook. Paddle checkout and prospect research require explicit server-side entitlements for every catalog plan, including a `prospect_research` quota; all quota policies are validated before release.

The JSON distinguishes `ok` from `launch_ready`:
- `ok` means local configuration and required-artifact checks have no errors.
- `launch_ready` is true only when there are no errors **and** no unverified runtime gates.

For release automation, use the stricter mode:

```bash
cd backend
python -m scripts.launch_preflight --require-launch-ready
```

The strict mode exits with status `2` if local checks pass but any runtime acceptance
gate remains a warning. It exits with status `1` for configuration/artifact errors and
`0` only when all checks pass. Since this local script cannot verify remote state, strict
mode intentionally blocks release until those gates are integrated with an authoritative
verification source or separately verified by the release process.

## What this does not prove

Warnings are intentional. A green local preflight is not evidence that a remote deploy
is running the latest commit, migrations have been applied to production, SMTP/Paddle/
WhatsApp credentials work, or a backup can be restored. Verify those independently
using the deployed health endpoint, database migration ledger, provider sandbox
transactions, and an isolated restore drill. Never put secret values in release reports.

## CI

Tests live in `backend/tests/test_launch_preflight.py` and exercise valid configuration,
secret validation, URL restrictions, partial provider configuration, billing-mode
consistency, missing operational artifacts, the distinction between local checks and
remote acceptance, and strict launch-gate exit behavior.
