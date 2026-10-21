"""Fail-closed subscription entitlement primitives.

This module is provider-neutral. It does not accept browser-supplied plan claims,
process payment webhooks, or unlock access on its own; callers must load subscription
and usage snapshots from trusted server-side persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


ACTIVE_STATUSES = frozenset({"active", "trialing"})


@dataclass(frozen=True)
class EntitlementDecision:
    allowed: bool
    reason: str
    remaining: int | None = None


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def evaluate_entitlement(
    *,
    subscription_status: str | None,
    period_starts_at: datetime | None,
    period_ends_at: datetime | None,
    feature: str,
    entitlements: Mapping[str, object] | None,
    usage: int | None = None,
    now: datetime | None = None,
) -> EntitlementDecision:
    """Evaluate one server-loaded feature entitlement and optional monthly quota.

    Missing/invalid state, naive datetimes, unknown status, expired periods, disabled
    features, and invalid usage fail closed. A None limit means the trusted plan
    explicitly grants unlimited quota; a missing limit is not treated as unlimited.
    """
    if not isinstance(feature, str) or not feature.strip():
        return EntitlementDecision(False, "invalid_feature")
    if subscription_status not in ACTIVE_STATUSES:
        return EntitlementDecision(False, "subscription_inactive")
    current = _aware_utc(now or datetime.now(timezone.utc))
    starts = _aware_utc(period_starts_at)
    ends = _aware_utc(period_ends_at)
    if current is None or starts is None or ends is None or ends <= starts:
        return EntitlementDecision(False, "invalid_billing_period")
    if current < starts:
        return EntitlementDecision(False, "billing_period_not_started")
    if current >= ends:
        return EntitlementDecision(False, "billing_period_expired")
    if not isinstance(entitlements, Mapping) or feature not in entitlements:
        return EntitlementDecision(False, "feature_not_entitled")

    policy = entitlements[feature]
    if not isinstance(policy, Mapping) or policy.get("enabled") is not True:
        return EntitlementDecision(False, "feature_disabled")
    limit = policy.get("monthly_limit")
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
    ):
        return EntitlementDecision(False, "invalid_quota_configuration")
    if limit is None:
        if "monthly_limit" not in policy:
            return EntitlementDecision(False, "quota_not_configured")
        return EntitlementDecision(True, "entitled", None)
    if isinstance(usage, bool) or not isinstance(usage, int) or usage < 0:
        return EntitlementDecision(False, "invalid_usage")
    remaining = max(0, limit - usage)
    if remaining == 0:
        return EntitlementDecision(False, "quota_exhausted", 0)
    return EntitlementDecision(True, "entitled", remaining)
