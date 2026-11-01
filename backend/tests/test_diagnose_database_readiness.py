from scripts.diagnose_database_readiness import (
    REQUIRED_COLUMNS,
    REQUIRED_MIGRATIONS,
    REQUIRED_TABLES,
    evaluate_schema_state,
)


def _complete_state():
    return evaluate_schema_state(
        local_migrations=REQUIRED_MIGRATIONS,
        applied_migrations=REQUIRED_MIGRATIONS,
        present_tables=REQUIRED_TABLES,
        present_columns=REQUIRED_COLUMNS,
    )


def test_complete_schema_snapshot_is_ready():
    result = _complete_state()
    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["summary"] == {"passed": 4, "failed": 0, "total": 4}


def test_missing_migration_is_named_in_diagnostic():
    result = evaluate_schema_state(
        local_migrations=REQUIRED_MIGRATIONS,
        applied_migrations=REQUIRED_MIGRATIONS[:-1],
        present_tables=REQUIRED_TABLES,
        present_columns=REQUIRED_COLUMNS,
    )
    assert result["ok"] is False
    ledger = next(check for check in result["checks"] if check["name"] == "migration_ledger")
    assert ledger["missing"] == ["056_billing_transaction_past_due.sql"]


def test_missing_repository_migration_is_separate_from_database_state():
    result = evaluate_schema_state(
        local_migrations=REQUIRED_MIGRATIONS[:-1],
        applied_migrations=REQUIRED_MIGRATIONS,
        present_tables=REQUIRED_TABLES,
        present_columns=REQUIRED_COLUMNS,
    )
    local = next(check for check in result["checks"] if check["name"] == "migration_files")
    ledger = next(check for check in result["checks"] if check["name"] == "migration_ledger")
    assert local["missing"] == ["056_billing_transaction_past_due.sql"]
    assert ledger["status"] == "pass"


def test_missing_table_and_column_are_independently_reported():
    tables = set(REQUIRED_TABLES)
    tables.remove("workspace_growth_schedules")
    columns = set(REQUIRED_COLUMNS)
    columns.remove(("whatsapp_outbound_deliveries", "lease_expires_at"))
    result = evaluate_schema_state(REQUIRED_MIGRATIONS, REQUIRED_MIGRATIONS, tables, columns)
    table_check = next(check for check in result["checks"] if check["name"] == "required_tables")
    column_check = next(check for check in result["checks"] if check["name"] == "required_columns")
    assert table_check["missing"] == ["workspace_growth_schedules"]
    assert column_check["missing"] == ["whatsapp_outbound_deliveries.lease_expires_at"]


def test_diagnostic_does_not_report_ready_when_schema_migrations_table_is_missing():
    tables = set(REQUIRED_TABLES)
    tables.remove("schema_migrations")
    result = evaluate_schema_state(REQUIRED_MIGRATIONS, [], tables, [])
    assert result["status"] == "not_ready"
    assert result["ok"] is False


def test_every_local_migration_is_checked_in_the_database_ledger():
    future_migration = "057_future_migration.sql"
    local = (*REQUIRED_MIGRATIONS, future_migration)
    result = evaluate_schema_state(
        local_migrations=local,
        applied_migrations=REQUIRED_MIGRATIONS,
        present_tables=REQUIRED_TABLES,
        present_columns=REQUIRED_COLUMNS,
    )
    ledger = next(check for check in result["checks"] if check["name"] == "migration_ledger")
    assert ledger["missing"] == [future_migration]
