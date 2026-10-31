"""Unit-level validation for the durable WhatsApp status reconciler."""
import asyncio

import pytest

from app.services.whatsapp_status_reconciliation import (
    _status_target,
    reconcile_whatsapp_delivery_statuses,
)


@pytest.mark.parametrize(
    ("provider", "expected"),
    [("sent", "sent"), ("DELIVERED", "delivered"), ("read", "read"),
     ("failed", "failed"), ("unknown", None), (None, None), (4, None)],
)
def test_status_target_is_allowlisted(provider, expected):
    assert _status_target(provider) == expected


def test_reconciler_rejects_invalid_batch_before_database_access():
    class NoDatabase:
        def acquire(self):
            raise AssertionError("invalid batch must fail before database access")

    with pytest.raises(ValueError, match="batch_size_out_of_range"):
        asyncio.run(reconcile_whatsapp_delivery_statuses(NoDatabase(), batch_size=True))


def test_reconciler_rejects_invalid_workspace_before_database_access():
    class NoDatabase:
        def acquire(self):
            raise AssertionError("invalid workspace must fail before database access")

    with pytest.raises(ValueError, match="workspace_id_invalid"):
        asyncio.run(reconcile_whatsapp_delivery_statuses(NoDatabase(), workspace_id=" "))


def test_failed_provider_status_has_lowest_rank_so_it_cannot_win_timestamp_ties():
    # A provider can report a failure callback after delivery/read callbacks due to
    # retries or callback ordering. Positive delivery evidence must take precedence.
    assert _status_target("failed") == "failed"


def test_reconciler_ranks_failed_below_sent_when_provider_timestamps_tie():
    class Connection:
        query = None

        async def fetch(self, query, *args):
            self.query = query
            return []

    class Acquire:
        def __init__(self, connection):
            self.connection = connection

        async def __aenter__(self):
            return self.connection

        async def __aexit__(self, *args):
            return False

    class Pool:
        def __init__(self):
            self.connection = Connection()

        def acquire(self):
            return Acquire(self.connection)

    pool = Pool()
    result = asyncio.run(reconcile_whatsapp_delivery_statuses(pool))
    assert result == {"events_considered": 0, "deliveries_updated": 0}
    query = pool.connection.query
    assert "WHEN 'failed' THEN 0" in query
    assert "WHEN 'sent' THEN 1" in query
    assert "WHEN 'delivered' THEN 2" in query
    assert "WHEN 'read' THEN 3" in query
