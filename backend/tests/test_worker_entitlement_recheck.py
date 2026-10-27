from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.services.subscription_store import SubscriptionStore


NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


class _Connection:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, _query, *_args):
        return self.row


class _Pool:
    def __init__(self, row):
        self.connection = _Connection(row)

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def _row(**overrides):
    value = {
        "status": "active",
        "billing_period_starts_at": NOW - timedelta(days=1),
        "billing_period_ends_at": NOW + timedelta(days=29),
        "entitlements": {"website_audits": {"enabled": True, "monthly_limit": 1}},
        "reservation_id": uuid4(),
        "reservation_feature": "website_audits",
        "reservation_status": "consumed",
        "reservation_starts_at": NOW - timedelta(days=1),
        "reservation_ends_at": NOW + timedelta(days=29),
        "usage": 1,
    }
    value.update(overrides)
    return value


@pytest.mark.asyncio
async def test_consumed_reservation_is_revalidated_without_charging_it_twice():
    reservation_id = uuid4()
    row = _row(reservation_id=reservation_id)
    row["reservation_id"] = reservation_id
    store = SubscriptionStore(_Pool(row))

    result = await store.validate_job_reservation(
        workspace_id="workspace-1",
        reservation_id=str(reservation_id),
        feature="website_audits",
        now=NOW,
    )

    assert result == {"allowed": True, "reason": "entitled", "reservation_status": "consumed"}


@pytest.mark.asyncio
async def test_worker_reservation_is_denied_after_subscription_cancellation():
    reservation_id = uuid4()
    row = _row(status="cancelled", reservation_id=reservation_id)
    store = SubscriptionStore(_Pool(row))

    result = await store.validate_job_reservation(
        workspace_id="workspace-1",
        reservation_id=str(reservation_id),
        feature="website_audits",
        now=NOW,
    )

    assert result["allowed"] is False
    assert result["reason"] == "subscription_inactive"


@pytest.mark.asyncio
async def test_worker_reservation_must_be_consumed_and_match_feature():
    reservation_id = uuid4()
    row = _row(reservation_id=reservation_id, reservation_status="released")
    store = SubscriptionStore(_Pool(row))

    result = await store.validate_job_reservation(
        workspace_id="workspace-1",
        reservation_id=str(reservation_id),
        feature="website_audits",
        now=NOW,
    )

    assert result == {"allowed": False, "reason": "reservation_not_active"}


@pytest.mark.asyncio
async def test_legacy_job_still_fails_closed_for_inactive_subscription():
    row = _row(status="cancelled")
    store = SubscriptionStore(_Pool(row))

    result = await store.check_feature_enabled(
        workspace_id="workspace-1", feature="website_audits", now=NOW
    )

    assert result == {"allowed": False, "reason": "subscription_inactive"}
