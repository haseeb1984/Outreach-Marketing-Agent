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
    # Duplicate delivery can contain changed payload data; the original event ID
    # remains idempotent when its tenant/subscription binding is unchanged.
    assert BillingLifecycleStore._same_event_identity(
        {**prior, "event_created_at": NOW + timedelta(seconds=1)}, event()
    )
