from app.api.platform_admin_routes import _billing_reconciliation_sql


def test_billing_reconciliation_is_read_only_and_uses_verified_ledgers():
    sql = _billing_reconciliation_sql().lower()
    assert "from workspace_subscriptions" in sql
    assert "from billing_transactions" in sql
    assert "from billing_provider_events" in sql
    assert "from workspace_memberships" in sql
    assert "from app_users" in sql
    assert "from platform_billing_plans" in sql
    assert "left join lateral" in sql
    assert "order by t.billed_at desc,t.transaction_id desc limit 1" in sql
    assert "order by e.event_created_at desc,e.received_at desc limit 1" in sql
    assert not any(token in sql for token in ("insert into ", "update ", "delete from ", "truncate "))


def test_billing_reconciliation_flags_payment_and_mapping_discrepancies():
    sql = _billing_reconciliation_sql()
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


def test_billing_reconciliation_latest_invoice_is_scoped_to_same_workspace_and_provider():
    sql = _billing_reconciliation_sql()
    assert "where t.workspace_id=w.id and t.provider=s.provider" in sql
    assert "where e.workspace_id=w.id and e.provider=s.provider" in sql
    assert "e.provider_subscription_id=s.provider_subscription_id" in sql
