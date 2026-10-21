from datetime import datetime, timedelta, timezone

import pytest

from app.services.entitlements import evaluate_entitlement


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
START = NOW - timedelta(days=1)
END = NOW + timedelta(days=29)
EMAIL = {"email_outreach": {"enabled": True, "monthly_limit": 100}}


def evaluate(**overrides):
    values = {
        "subscription_status": "active",
        "period_starts_at": START,
        "period_ends_at": END,
        "feature": "email_outreach",
        "entitlements": EMAIL,
        "usage": 20,
        "now": NOW,
    }
    values.update(overrides)
    return evaluate_entitlement(**values)


def test_active_subscription_with_configured_quota_is_allowed():
    decision = evaluate()
    assert decision.allowed is True
    assert decision.reason == "entitled"
    assert decision.remaining == 80


@pytest.mark.parametrize("status", [None, "", "past_due", "cancelled", "incomplete", "unknown"])
def test_non_active_or_unknown_subscription_fails_closed(status):
    decision = evaluate(subscription_status=status)
    assert decision.allowed is False
    assert decision.reason == "subscription_inactive"


def test_trialing_is_allowed_only_with_a_valid_current_period():
    assert evaluate(subscription_status="trialing").allowed is True
    decision = evaluate(subscription_status="trialing", period_ends_at=NOW)
    assert decision.reason == "billing_period_expired"


def test_missing_or_naive_billing_dates_fail_closed():
    assert evaluate(period_starts_at=None).reason == "invalid_billing_period"
    assert evaluate(period_starts_at=datetime(2026, 10, 20)).reason == "invalid_billing_period"


def test_future_and_expired_billing_periods_are_rejected():
    assert evaluate(period_starts_at=NOW + timedelta(seconds=1)).reason == "billing_period_not_started"
    assert evaluate(period_ends_at=NOW - timedelta(seconds=1)).reason == "billing_period_expired"


def test_missing_disabled_and_malformed_features_fail_closed():
    assert evaluate(entitlements=None).reason == "feature_not_entitled"
    assert evaluate(entitlements={}).reason == "feature_not_entitled"
    assert evaluate(entitlements={"email_outreach": {"enabled": False, "monthly_limit": 10}}).reason == "feature_disabled"
    assert evaluate(entitlements={"email_outreach": {"enabled": True}}).reason == "quota_not_configured"


def test_quota_exhaustion_and_bad_usage_fail_closed():
    assert evaluate(usage=100).reason == "quota_exhausted"
    assert evaluate(usage=-1).reason == "invalid_usage"
    assert evaluate(usage=True).reason == "invalid_usage"


def test_explicit_unlimited_quota_is_not_confused_with_missing_limit():
    decision = evaluate(entitlements={"email_outreach": {"enabled": True, "monthly_limit": None}}, usage=None)
    assert decision.allowed is True
    assert decision.remaining is None


def test_boolean_or_negative_quota_configuration_is_rejected():
    assert evaluate(entitlements={"email_outreach": {"enabled": True, "monthly_limit": True}}).reason == "invalid_quota_configuration"
    assert evaluate(entitlements={"email_outreach": {"enabled": True, "monthly_limit": -1}}).reason == "invalid_quota_configuration"
