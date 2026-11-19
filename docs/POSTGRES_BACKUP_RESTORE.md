# PostgreSQL backup and restore runbook

Run from the `backend/` directory on a trusted host with compatible `pg_dump` and `pg_restore` tools. Keep database URLs and credentials in environment variables or a secret manager; do not commit them.

## Create a backup

```sh
export DATABASE_URL='postgresql://...'
export BACKUP_DIR='/secure/backups/outreach-marketing-agent'
python scripts/database_backup.py backup
```

The script writes a timestamped custom-format dump and a SHA-256 sidecar. Restrict access to the backup directory and apply encrypted storage and a retention policy suitable for customer data.

## Verify an archive

```sh
python scripts/database_backup.py verify /secure/backups/outreach-marketing-agent/outreach-db-YYYYMMDDTHHMMSSZ.dump
```

Verification checks the checksum and reads the archive directory with `pg_restore --list`. This is not a full recovery test.

## Restore into a separate empty recovery database

Provision an empty staging/recovery database first. Set `SOURCE_DATABASE_URL`, `RESTORE_DATABASE_URL` and `CONFIRM_RESTORE=YES`, then run:

```sh
python scripts/database_backup.py restore /secure/backups/outreach-marketing-agent/outreach-db-YYYYMMDDTHHMMSSZ.dump
```

The tool refuses the same source/target host, port and database name, requires explicit confirmation, and runs `pg_restore` with `--single-transaction` (so a failed restore is rolled back) without using `pg_restore --clean`. The target must be empty; the tool does not automatically clear an existing database. Validate migration history, core tables, tenant isolation and representative application reads after the restore.

## Release evidence

Record the backup timestamp, checksum, source environment label (never its URL), archive size, restore target label, tool versions, restore duration and validation results. Define and rehearse an RPO/RTO. Do not claim backup/restore acceptance until an actual restore succeeds in a separate environment.


## Safe local retention cleanup

The backup tool includes an explicit retention-prune operation. It is **dry-run by default** and only considers regular, non-symlink files named `outreach-db-*.dump` in the selected backup directory. It never recursively scans directories or deletes unrelated exports.

Preview candidates older than 30 days while preserving at least the newest 2 archives:

```sh
python scripts/database_backup.py prune --older-than-days 30 --keep-at-least 2
```

Only after reviewing the printed candidates, add `--apply` to delete those archives and their matching SHA-256 sidecars:

```sh
python scripts/database_backup.py prune --older-than-days 30 --keep-at-least 2 --apply
```

Choose retention days and minimum copies only after the operator/legal schedule, recovery objectives, storage encryption, off-host copy and legal-hold requirements are approved. This command is not a remote backup, scheduler or legal-retention policy. Do not schedule destructive pruning until those controls and a successful separate-environment restore drill are evidenced. Keep backup directories access-restricted and encrypted at rest; a checksum detects accidental changes but does not provide encryption or authenticity.
