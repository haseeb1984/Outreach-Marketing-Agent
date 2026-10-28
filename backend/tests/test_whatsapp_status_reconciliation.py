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
