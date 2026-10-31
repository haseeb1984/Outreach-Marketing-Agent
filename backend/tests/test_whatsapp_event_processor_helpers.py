from datetime import datetime, timezone

import pytest

from app.services.whatsapp_event_processor import _effective_inbound_timestamp, _is_opt_in, _is_opt_out, _text, _timestamp


@pytest.mark.parametrize("body", ["STOP", " stop ", "STOP!", "Unsubscribe.", "cancel", "END;", "QUIT?"])
def test_standalone_opt_out_commands_are_recognized(body):
    assert _is_opt_out(body) is True


@pytest.mark.parametrize("body", [None, "", "please stop sending", "STOP messaging me", "nonstop", "START"])
def test_opt_out_does_not_match_ordinary_prose(body):
    assert _is_opt_out(body) is False


@pytest.mark.parametrize("body", ["START", "start!", "UNSTOP", "subscribe."])
def test_explicit_start_family_commands_are_recognized(body):
    assert _is_opt_in(body) is True


@pytest.mark.parametrize("body", [None, "hello", "please start the campaign", "unsubscribe me tomorrow"])
def test_opt_in_does_not_match_ordinary_prose(body):
    assert _is_opt_in(body) is False


def test_text_extraction_bounds_message_body():
    kind, body = _text({"type": "text", "text": {"body": "x" * 12000}})
    assert kind == "text"
    assert body == "x" * 10000


def test_non_text_message_has_no_body():
    assert _text({"type": "image", "image": {"id": "media"}}) == ("image", None)


def test_timestamp_parses_epoch_to_utc():
    result = _timestamp("1792713600")
    assert result is not None
    assert result.tzinfo == timezone.utc


@pytest.mark.parametrize("value", [None, {}, "not-a-time", float("inf"), -10**100])
def test_invalid_timestamps_return_none(value):
    assert _timestamp(value) is None


def test_effective_inbound_timestamp_uses_provider_time_when_not_future():
    received = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    provider = datetime(2026, 10, 23, 11, 55, tzinfo=timezone.utc)
    assert _effective_inbound_timestamp(provider, received) == provider


def test_effective_inbound_timestamp_clamps_future_provider_time():
    received = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    provider = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    assert _effective_inbound_timestamp(provider, received) == received


def test_effective_inbound_timestamp_falls_back_to_server_receipt_time():
    received = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    assert _effective_inbound_timestamp(None, received) == received


def test_event_processor_rejects_invalid_workspace_scope_before_database_access():
    import asyncio
    from app.services.whatsapp_event_processor import process_pending_whatsapp_events

    class NoDatabase:
        def acquire(self):
            raise AssertionError("invalid workspace must be rejected before DB access")

    with pytest.raises(ValueError, match="workspace_id_invalid"):
        asyncio.run(process_pending_whatsapp_events(NoDatabase(), workspace_id=" "))


def test_event_processor_rejects_boolean_batch_size():
    import asyncio
    from app.services.whatsapp_event_processor import process_pending_whatsapp_events

    class NoDatabase:
        def acquire(self):
            raise AssertionError("invalid batch must be rejected before DB access")

    with pytest.raises(ValueError, match="batch_size_out_of_range"):
        asyncio.run(process_pending_whatsapp_events(NoDatabase(), batch_size=True))


def test_workspace_scoped_worker_only_claims_active_accounts_for_that_workspace():
    import asyncio
    from app.services.whatsapp_event_processor import process_pending_whatsapp_events

    captured = {}

    class Transaction:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False

    class Connection:
        def transaction(self): return Transaction()
        async def fetchrow(self, query, *args):
            captured["query"] = query
            captured["args"] = args
            return None

    class Acquire:
        async def __aenter__(self): return Connection()
        async def __aexit__(self, *args): return False

    class Pool:
        def acquire(self): return Acquire()

    result = asyncio.run(process_pending_whatsapp_events(Pool(), workspace_id="workspace-a", batch_size=1))
    assert result == {"processed": 0, "messages_saved": 0, "statuses_saved": 0, "unmapped": 0, "failed": 0}
    assert "EXISTS" in captured["query"]
    assert "a.workspace_id=$1 AND a.status='active'" in captured["query"]
    assert captured["args"] == ("workspace-a",)


def test_failed_status_rank_is_lower_than_positive_delivery_evidence():
    import inspect
    from app.services import whatsapp_event_processor

    source = inspect.getsource(whatsapp_event_processor.process_pending_whatsapp_events)
    assert "WHEN 'sent' THEN 1" in source
    assert "WHEN 'failed' THEN 0" in source
    assert "WHEN 'delivered' THEN 2" in source
    assert "WHEN 'read' THEN 3" in source


def test_phone_mapping_requires_exactly_one_workspace_prospect():
    from uuid import uuid4
    from app.services.whatsapp_event_processor import _unique_prospect_id

    prospect_id = uuid4()
    assert _unique_prospect_id([{"id": prospect_id}]) == prospect_id
    assert _unique_prospect_id([]) is None
    assert _unique_prospect_id([{"id": prospect_id}, {"id": uuid4()}]) is None
    assert _unique_prospect_id([{}]) is None


def test_event_processor_uses_safe_prospect_id_after_unique_mapping():
    import inspect
    from app.services import whatsapp_event_processor

    source = inspect.getsource(whatsapp_event_processor.process_pending_whatsapp_events)
    assert 'prospect["id"]' not in source
    assert "if prospect_id:" in source
    assert "workspace_id, account_id, prospect_id," in source

def test_event_processor_uses_persisted_conversation_prospect_for_contact_actions():
    import inspect
    from app.services import whatsapp_event_processor

    source = inspect.getsource(whatsapp_event_processor.process_pending_whatsapp_events)
    assert "RETURNING id,prospect_id" in source
    assert 'associated_prospect_id = conversation["prospect_id"]' in source
    assert "if associated_prospect_id:" in source
    assert "workspace_id, account_id, associated_prospect_id," in source