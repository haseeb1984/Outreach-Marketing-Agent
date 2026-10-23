"""Small deterministic tests for Meta delivery-state normalization."""
from app.services.whatsapp_event_processor import _delivery_status_target


def test_known_provider_states_map_to_internal_queue_states():
    assert _delivery_status_target("sent") == "sent"
    assert _delivery_status_target("DELIVERED") == "delivered"
    assert _delivery_status_target("read") == "read"
    assert _delivery_status_target("failed") == "failed"


def test_unknown_or_malformed_provider_states_are_ignored():
    assert _delivery_status_target("deleted") is None
    assert _delivery_status_target("") is None
    assert _delivery_status_target(None) is None
    assert _delivery_status_target(42) is None
