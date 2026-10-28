# Read-only database readiness diagnostics

The API's `/ready` endpoint intentionally returns a generic `database_schema_not_migrated`
reason rather than listing internal schema details publicly. To identify the missing
migration ledger entries, tables, and columns, run this diagnostic from the backend
directory in an authorized environment with `DATABASE_URL` configured:

```bash
python -m scripts.diagnose_database_readiness
```

The command is **read-only**: it issues SELECT/catalog queries only and never applies a
migration or writes to the database. It emits JSON with separate checks for local
migration files, the database migration ledger, required tables, and required columns.
The output never includes the connection string or raw database exception text.

Exit codes:
- `0`: all schema checks passed.
- `1`: the database is reachable but required schema state is incomplete.
- `2`: the database URL is missing or inspection could not be completed.

Run this only with a database account authorized to inspect the target environment.
Use production access carefully; this command is not a substitute for backups, migration
review, or the approved migration procedure. Do not use a production URL in shared logs.
