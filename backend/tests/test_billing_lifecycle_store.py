from datetime import datetime, timedelta, timezone

import pytest

from app.services.billing_lifecycle_store import BillingLifecycleStore, VerifiedBillingEvent


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def event(**overrides):
    values = {
        "provider": "test-provider",
        "event_id": "evt_12345678",
        "workspace_id": "workspace-1",
        "provider_customer_id": "cus_123",
        "provider_subscription_id": "sub_123",
        "plan_slug": "starter",
        "event_created_at": NOW,
        "subscription_status": "active",
        "period_starts_at": NOW - timedelta(days=1),
        "period_ends_at": NOW + timedelta(days=29),
        "entitlements": {"email_outreach": {"enabled": True, "monthly_limit": 100}},
    }
    values.update(overrides)
    return VerifiedBillingEvent(**values)


def test_valid_verified_event_passes_boundary_validation():
    BillingLifecycleStore._validate(event())


@pytest.mark.parametrize("status", ["unknown", "", "ACTIVE", None, [], {}])
def test_unknown_or_wrong_type_subscription_status_is_rejected(status):
    with pytest.raises(ValueError, match="invalid_subscription_status"):
        BillingLifecycleStore._validate(event(subscription_status=status))


@pytest.mark.parametrize("field,value,error", [
    ("provider", "", "invalid_provider"),
    ("event_id", "e" * 301, "invalid_event_id"),
    ("workspace_id", " ", "invalid_workspace_id"),
    ("provider_subscription_id", "", "invalid_provider_subscription_id"),
    ("plan_slug", "p" * 81, "invalid_plan_slug"),
])
def test_required_identity_fields_are_validated(field, value, error):
    with pytest.raises(ValueError, match=error):
        BillingLifecycleStore._validate(event(**{field: value}))


@pytest.mark.parametrize("value", ["", "  ", "c" * 301, 42])
def test_invalid_optional_customer_id_is_rejected(value):
    with pytest.raises(ValueError, match="invalid_provider_customer_id"):
        BillingLifecycleStore._validate(event(provider_customer_id=value))


def test_naive_event_or_billing_timestamps_are_rejected():
    with pytest.raises(ValueError, match="timezone_required"):
        BillingLifecycleStore._validate(event(event_created_at=datetime(2026, 10, 21)))


def test_reversed_billing_period_is_rejected():
    with pytest.raises(ValueError, match="invalid_billing_period"):
        BillingLifecycleStore._validate(event(period_starts_at=NOW, period_ends_at=NOW))


def test_non_json_entitlements_are_rejected():
    with pytest.raises(ValueError, match="invalid_entitlements"):
        BillingLifecycleStore._validate(event(entitlements={"x": object()}))


def test_non_finite_entitlements_are_rejected():
    with pytest.raises(ValueError, match="invalid_entitlements"):
        BillingLifecycleStore._validate(event(entitlements={"x": float("nan")}))


def test_oversized_event_identifier_is_rejected():
    with pytest.raises(ValueError, match="invalid_event_id"):
        BillingLifecycleStore._validate(event(event_id="e" * 301))


def test_oversized_entitlements_are_rejected():
    with pytest.raises(ValueError, match="entitlements_too_large"):
        BillingLifecycleStore._validate(event(entitlements={"data": "x" * 100_001}))



def test_duplicate_event_identity_must_match_tenant_subscription_and_timestamp():
    prior = {
        "workspace_id": "workspace-1",
        "provider_subscription_id": "sub_123",
        "event_created_at": NOW,
    }
    assert BillingLifecycleStore._same_event_identity(prior, event())
    assert not BillingLifecycleStore._same_event_identity(
        {**prior, "workspace_id": "workspace-2"}, event()
    )
    assert not BillingLifecycleStore._same_event_identity(
        {**prior, "provider_subscription_id": "sub_other"}, event()
    )
    # Reusing the same provider event ID with a different provider timestamp
    # is an identity collision, not a legitimate duplicate delivery.
    assert not BillingLifecycleStore._same_event_identity(
        {**prior, "event_created_at": NOW + timedelta(seconds=1)}, event()
    )

@pytest.mark.parametrize(
    "prior,subscription_id,invoice_number,expected",
    [
        ({"provider_subscription_id": "sub_1", "invoice_number": "INV-1"}, "sub_1", "INV-1", True),
        ({"provider_subscription_id": "sub_1", "invoice_number": "INV-1"}, None, None, True),
        ({"provider_subscription_id": "sub_1", "invoice_number": "INV-1"}, "sub_2", "INV-1", False),
        ({"provider_subscription_id": "sub_1", "invoice_number": "INV-1"}, "sub_1", "INV-2", False),
        ({"provider_subscription_id": None, "invoice_number": None}, "sub_2", "INV-2", True),
    ],
)
def test_transaction_identity_cannot_be_rebound(prior, subscription_id, invoice_number, expected):
    assert BillingLifecycleStore._same_transaction_identity(
        prior, subscription_id=subscription_id, invoice_number=invoice_number
    ) is expected

@pytest.mark.parametrize("field,value,error", [
    ("subscription_id", "", "invalid_subscription_id"),
    ("subscription_id", " ", "invalid_subscription_id"),
    ("invoice_number", "", "invalid_invoice_number"),
    ("invoice_number", " ", "invalid_invoice_number"),
    ("currency_code", "US", "invalid_currency_code"),
    ("currency_code", "usd", "invalid_currency_code"),
    ("currency_code", "U$D", "invalid_currency_code"),
])
def test_transaction_optional_identifiers_and_currency_are_strictly_validated(field, value, error):
    values = {
        "event_id": "evt_tx_123",
        "event_created_at": NOW,
        "transaction_id": "txn_123",
        "workspace_id": "workspace-1",
        "subscription_id": "sub_123",
        "invoice_number": "INV-123",
        "status": "completed",
        "currency_code": "USD",
        "total_minor": "1000",
    }
    values[field] = value
    with pytest.raises(ValueError, match=error):
        # Exercise the same boundary validation without opening a database connection.
        BillingLifecycleStore._validate_transaction(**values)

def test_duplicate_transaction_event_must_match_original_workspace_and_transaction_identity():
    prior = {
        "transaction_id": "txn_123",
        "event_created_at": NOW,
        "workspace_id": "workspace-1",
        "provider_subscription_id": "sub_123",
        "invoice_number": "INV-123",
    }
    kwargs = {
        "transaction_id": "txn_123",
        "event_created_at": NOW,
        "workspace_id": "workspace-1",
        "subscription_id": "sub_123",
        "invoice_number": "INV-123",
    }
    assert BillingLifecycleStore._same_transaction_event_identity(prior, **kwargs)
    assert not BillingLifecycleStore._same_transaction_event_identity(
        {**prior, "workspace_id": "workspace-2"}, **kwargs
    )
    assert not BillingLifecycleStore._same_transaction_event_identity(
        {**prior, "transaction_id": "txn_other"}, **kwargs
    )
    assert not BillingLifecycleStore._same_transaction_event_identity(
        {**prior, "invoice_number": "INV-OTHER"}, **kwargs
    )

@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_subscription_id", None),
        ("invoice_number", None),
        ("provider_subscription_id", "sub_other"),
        ("invoice_number", "INV-OTHER"),
    ],
)
def test_duplicate_transaction_event_requires_exact_nullable_identity(field, value):
    prior = {
        "transaction_id": "txn_123",
        "event_created_at": NOW,
        "workspace_id": "workspace-1",
        "provider_subscription_id": "sub_123",
        "invoice_number": "INV-123",
    }
    kwargs = {
        "transaction_id": "txn_123",
        "event_created_at": NOW,
        "workspace_id": "workspace-1",
        "subscription_id": "sub_123",
        "invoice_number": "INV-123",
    }
    assert not BillingLifecycleStore._same_transaction_event_identity(
        {**prior, field: value}, **kwargs
    )

def test_verified_subscription_event_fingerprint_is_stable_and_covers_entire_snapshot():
    original = event()
    same = event(entitlements={"email_outreach": {"monthly_limit": 100, "enabled": True}})
    changed_status = event(subscription_status="cancelled")
    changed_plan = event(plan_slug="pro")
    assert BillingLifecycleStore._event_fingerprint(original) == BillingLifecycleStore._event_fingerprint(same)
    assert BillingLifecycleStore._event_fingerprint(original) != BillingLifecycleStore._event_fingerprint(changed_status)
    assert BillingLifecycleStore._event_fingerprint(original) != BillingLifecycleStore._event_fingerprint(changed_plan)


def test_verified_transaction_event_fingerprint_covers_all_mutable_fields():
    base = {
        "event_id": "evt_tx_123", "event_created_at": NOW,
        "transaction_id": "txn_123", "workspace_id": "workspace-1",
        "subscription_id": "sub_123", "invoice_number": "INV-123",
        "status": "completed", "currency_code": "USD", "total_minor": "1000",
    }
    fingerprint = BillingLifecycleStore._transaction_event_fingerprint(**base)
    assert fingerprint == BillingLifecycleStore._transaction_event_fingerprint(**base)
    for field, value in (("status", "payment_failed"), ("currency_code", "EUR"),
                         ("total_minor", "1001"), ("invoice_number", "INV-124"),
                         ("subscription_id", None), ("workspace_id", "workspace-2")):
        assert fingerprint != BillingLifecycleStore._transaction_event_fingerprint(**{**base, field: value})


def test_subscription_fingerprint_normalizes_equivalent_timezone_offsets():
    offset = timezone(timedelta(hours=5))
    equivalent = event(
        event_created_at=NOW.astimezone(offset),
        period_starts_at=(NOW - timedelta(days=1)).astimezone(offset),
        period_ends_at=(NOW + timedelta(days=29)).astimezone(offset),
    )
    assert BillingLifecycleStore._event_fingerprint(event()) == BillingLifecycleStore._event_fingerprint(equivalent)


def test_transaction_fingerprint_normalizes_equivalent_timezone_offsets():
    values = {
        "event_id": "evt_tx_123", "event_created_at": NOW,
        "transaction_id": "txn_123", "workspace_id": "workspace-1",
        "subscription_id": "sub_123", "invoice_number": "INV-123",
        "status": "completed", "currency_code": "USD", "total_minor": "1000",
    }
    equivalent = {**values, "event_created_at": NOW.astimezone(timezone(timedelta(hours=5)))}
    assert BillingLifecycleStore._transaction_event_fingerprint(**values) == BillingLifecycleStore._transaction_event_fingerprint(**equivalent)


def test_paddle_past_due_transaction_status_passes_boundary_validation():
    BillingLifecycleStore._validate_transaction(
        event_id="evt_tx_past_due",
        event_created_at=NOW,
        transaction_id="txn_past_due",
        workspace_id="workspace-1",
        subscription_id="sub_123",
        invoice_number=None,
        status="past_due",
        currency_code="USD",
        total_minor="1000",
    )
