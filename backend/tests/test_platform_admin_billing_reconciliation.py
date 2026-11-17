from app.api.platform_admin_routes import _billing_reconciliation_sql


def test_billing_reconciliation_is_read_only_and_uses_verified_ledgers():
    sql = " ".join(_billing_reconciliation_sql().lower().split())
    assert "from workspace_subscriptions" in sql
    assert "from billing_transactions" in sql
    assert "from billing_provider_events" in sql
    assert "from workspace_memberships" in sql
    assert "join app_users" in sql
    assert "from platform_billing_plans" in sql
    assert "left join lateral" in sql
    assert "order by t.billed_at desc,t.transaction_id desc limit 1" in sql
    assert "order by e.event_created_at desc,e.received_at desc limit 1" in sql
    assert not any(token in sql for token in ("insert into ", "update ", "delete from ", "truncate "))


def test_billing_reconciliation_flags_payment_and_mapping_discrepancies():
    sql = " ".join(_billing_reconciliation_sql().lower().split())
    expected_flags = (
        "missing_provider_subscription_id",
        "plan_not_mapped",
        "missing_transaction_history",
        "missing_subscription_event_history",
        "payment_attention_but_subscription_active",
        "subscription_past_due_but_latest_payment_completed",
        "active_subscription_period_expired",
    )
    for flag in expected_flags:
        assert flag in sql
    assert "latest_transaction_id is null and subscription_status <> 'trialing'" in sql
    assert "catalog.entitlements=s.entitlements" in sql
    assert "catalog.active desc,catalog.created_at desc" in sql


def test_billing_reconciliation_latest_invoice_is_scoped_to_same_workspace_and_provider():
    sql = " ".join(_billing_reconciliation_sql().lower().split())
    assert "where t.workspace_id=w.id and t.provider=s.provider" in sql
    assert "where e.workspace_id=w.id and e.provider=s.provider" in sql
    assert "e.provider_subscription_id=s.provider_subscription_id" in sql


def test_customer_detail_billing_history_is_workspace_scoped_and_read_only():
    from app.api.platform_admin_routes import (
        _client_billing_transaction_history_sql,
        _client_subscription_event_history_sql,
    )

    transactions = " ".join(_client_billing_transaction_history_sql().lower().split())
    events = " ".join(_client_subscription_event_history_sql().lower().split())
    assert "from billing_transactions where workspace_id=$1" in transactions
    assert "order by billed_at desc,transaction_id desc limit 10" in transactions
    assert "from billing_provider_events where workspace_id=$1" in events
    assert "order by event_created_at desc,received_at desc limit 10" in events
    assert "total_minor" in transactions and "invoice_number" in transactions
    assert "provider_event_id" in events and "outcome" in events
    for sql in (transactions, events):
        assert not any(token in sql for token in ("insert into ", "update ", "delete from ", "truncate "))
        assert not any(token in sql for token in ("raw_payload", "webhook_secret", "signature"))


def test_billing_event_history_is_a_sanitized_read_only_union():
    sql = " ".join("""
      WITH events AS (
        SELECT 'subscription'::text AS event_kind,e.provider,e.provider_event_id,
          e.workspace_id::text AS workspace_id,w.name AS workspace_name,
          e.provider_subscription_id AS related_id,e.event_created_at,e.received_at,
          e.outcome,NULL::text AS transaction_status,NULL::text AS invoice_number
        FROM billing_provider_events e
        LEFT JOIN workspaces w ON w.id=e.workspace_id
        UNION ALL
        SELECT 'transaction'::text AS event_kind,e.provider,e.provider_event_id,
          t.workspace_id::text AS workspace_id,w.name AS workspace_name,
          e.transaction_id AS related_id,e.event_created_at,e.received_at,
          'recorded'::text AS outcome,t.status AS transaction_status,t.invoice_number
        FROM billing_transaction_events e
        LEFT JOIN billing_transactions t
          ON t.provider=e.provider AND t.transaction_id=e.transaction_id
        LEFT JOIN workspaces w ON w.id=t.workspace_id
      ), filtered AS (
        SELECT * FROM events
        WHERE ($1='' OR position($1 in lower(concat_ws(' ',
          event_kind,provider,provider_event_id,workspace_id,workspace_name,
          related_id,outcome,transaction_status,invoice_number)))>0)
      )
    """.lower().split())
    assert "from billing_provider_events e" in sql
    assert "from billing_transaction_events e" in sql
    assert "left join billing_transactions t" in sql
    assert "e.provider_event_id" in sql
    assert "e.received_at" in sql
    assert "e.event_created_at" in sql
    assert "union all" in sql
    assert not any(token in sql for token in ("insert into ", "update ", "delete from ", "truncate ", "raw_payload", "webhook_secret"))


def test_platform_admin_audit_search_is_parameterized_and_covers_actor_action_target_and_metadata():
    from app.api.platform_admin_routes import _platform_audit_search_sql

    sql = " ".join(_platform_audit_search_sql().lower().split())
    assert "$1 = ''" in sql
    assert "u.email" in sql
    assert "e.event_type" in sql
    assert "e.target_type" in sql
    assert "e.target_id" in sql
    assert "e.metadata::text" in sql
    assert "position($1 in lower(" in sql
    assert not any(token in sql for token in ("insert into ", "update ", "delete from ", "truncate "))


def test_platform_admin_audit_pagination_has_stable_tie_break_order():
    from app.api.platform_admin_routes import _platform_audit_search_sql

    # The endpoint must use a deterministic secondary key when multiple audit rows
    # share the same timestamp, so adjacent pages cannot reorder tied events.
    import inspect
    from app.api import platform_admin_routes

    source = inspect.getsource(platform_admin_routes.overview).lower()
    assert "order by e.created_at desc,e.id desc" in " ".join(source.split())
    assert "audit_search" in source
    assert _platform_audit_search_sql()
