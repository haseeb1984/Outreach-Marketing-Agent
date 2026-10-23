from datetime import datetime, timezone

import pytest

from app.services.whatsapp_event_processor import _is_opt_in, _is_opt_out, _text, _timestamp


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
