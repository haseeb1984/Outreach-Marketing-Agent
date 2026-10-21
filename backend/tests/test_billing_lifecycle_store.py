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


@pytest.mark.parametrize("status", ["unknown", "", "ACTIVE", None])
def test_unknown_subscription_status_is_rejected(status):
    with pytest.raises(ValueError, match="invalid_subscription_status"):
        BillingLifecycleStore._validate(event(subscription_status=status))


def test_naive_event_or_billing_timestamps_are_rejected():
    with pytest.raises(ValueError, match="timezone_required"):
        BillingLifecycleStore._validate(event(event_created_at=datetime(2026, 10, 21)))


def test_reversed_billing_period_is_rejected():
    with pytest.raises(ValueError, match="invalid_billing_period"):
        BillingLifecycleStore._validate(event(period_starts_at=NOW, period_ends_at=NOW))


def test_non_json_entitlements_are_rejected():
    with pytest.raises(ValueError, match="invalid_entitlements"):
        BillingLifecycleStore._validate(event(entitlements={"x": object()}))


def test_oversized_event_identifier_is_rejected():
    with pytest.raises(ValueError, match="invalid_event_id"):
        BillingLifecycleStore._validate(event(event_id="e" * 301))
