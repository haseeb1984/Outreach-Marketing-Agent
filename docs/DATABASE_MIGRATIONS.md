# Database Migration Guide

This guide is shipped with the application source so the database can be brought up to the schema expected by the current `main` branch.

## Current production baseline reviewed on 2026-11-27

The connected Neon production database reported 64 applied migrations, latest:
`064_daily_prospect_research_quota.sql`.

The repository contains migrations 001 through 071. The following seven files were therefore pending at the time of that read-only check:

1. `065_website_content_briefs.sql`
2. `066_website_content_articles.sql`
3. `067_wordpress_content_delivery.sql`
4. `068_project_scoped_wordpress_connections.sql`
5. `069_workspace_research_history.sql`
6. `070_campaign_project_relationship.sql`
7. `071_crm_prospect_project_relationship.sql`

**Re-check the live migration ledger immediately before applying.** The list above is a dated observation, not a guarantee that the database has not changed since then.

## What the migrations add

- 065: persistent workspace/project-scoped editorial briefs.
- 066: article draft, outline, SEO metadata and review fields on editorial briefs.
- 067: workspace WordPress connection records and CMS delivery state.
- 068: project-scoped WordPress connections, retaining a workspace-level fallback.
- 069: workspace-scoped prospect and creator research history.
- 070: optional campaign-to-project relationship with workspace-safe referential integrity.
- 071: optional CRM-prospect-to-project relationship with workspace-safe referential integrity.

Existing campaign and prospect records remain unlinked by default; these migrations do not require creating project records for existing data.

## Before running

1. Take and verify a current Neon backup/restore point according to the account's recovery settings.
2. Confirm that the connection string targets the intended production Neon project, branch and database. Never paste the connection string into chat or commit it.
3. Compare the live ledger with the migration files in `backend/migrations/`.
4. Ensure the application release being prepared is the same `main` commit whose migrations you intend to apply.
5. Schedule a maintenance window if required by your operating procedures.

## Apply using the repository's migration runner

The project already includes a transactional, ordered migration runner. It skips filenames already recorded in `schema_migrations`, applies each pending SQL file in its own transaction, and records the filename only after that migration succeeds. It is not run automatically at API startup.

From the repository root, in a Python environment with `backend/requirements.txt` installed:

```bash
cd backend
export DATABASE_URL='postgresql://...'
python -m app.db.migrations
```

Set `DATABASE_URL` in your shell/secret manager; do not replace the example with a real credential in this document. On Windows PowerShell, set it for the current terminal with:

```powershell
$env:DATABASE_URL = 'postgresql://...'
python -m app.db.migrations
```

The runner applies every migration file not already in the ledger, in filename order. Do not manually execute the same SQL files and then run the runner unless you have also correctly reconciled the ledger; otherwise the runner will try to apply them again.

## Verify after applying

Run this read-only query against the same database:

```sql
SELECT count(*) AS applied_migrations,
       min(version) AS first_migration,
       max(version) AS latest_migration,
       max(applied_at) AS last_applied_at
FROM schema_migrations;
```

For this repository snapshot, the expected result is 71 applied migrations with latest version `071_crm_prospect_project_relationship.sql`.

Confirm the new schema objects/columns:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'website_content_briefs',
    'workspace_wordpress_connections',
    'workspace_research_runs'
  )
ORDER BY table_name;

SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (
    (table_name = 'website_content_briefs' AND column_name IN
      ('article_body', 'cms_status', 'cms_connection_id'))
    OR (table_name = 'workspace_wordpress_connections' AND column_name = 'project_id')
    OR (table_name = 'outreach_campaigns' AND column_name = 'project_id')
    OR (table_name = 'crm_prospects' AND column_name = 'project_id')
  )
ORDER BY table_name, column_name;
```

Expected: the three tables exist and the queried columns are present. The migration ledger should show each filename exactly once.

## Alternative: GitHub Actions

The repository also provides `.github/workflows/neon-migrations.yml`. It is manually dispatched and requires the workflow input `confirm` to equal `apply`, plus the GitHub Actions secret `DATABASE_URL` pointing to the intended database. Review the workflow and target secret before dispatching it. Do not trigger this workflow accidentally.

## Failure and recovery

Each migration is transactional: if its SQL fails, that migration's transaction and ledger insert roll back. Earlier migrations in the same run may already have committed. Fix the underlying issue and rerun the migration runner; it will skip the already-recorded files.

These migrations are forward-only; this repository does not provide automatic down migrations. Do not try to reverse them by dropping tables/columns. If recovery is required, use the verified Neon restore procedure and assess any writes made after the backup.

## Release hand-off checklist

- [ ] Confirm production project, branch and database.
- [ ] Verify backup/restore point.
- [ ] Re-check pending migration filenames.
- [ ] Apply with `python -m app.db.migrations` or the reviewed manual workflow, not both simultaneously.
- [ ] Verify ledger and schema objects.
- [ ] Run backend readiness diagnostics and application acceptance checks.
- [ ] Record the applied migration count and timestamp in the release notes.
