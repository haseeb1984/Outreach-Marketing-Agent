import logging

from app.services.secret_safe_logging import install_secret_redaction, redact_text, _safe


def test_redact_common_inline_credentials():
    message = (
        "password=hunter2 Authorization: Bearer abc.def.ghi "
        "db=postgres://service:secretpass@db.example.test/app"
    )
    result = redact_text(message)
    assert "hunter2" not in result
    assert "abc.def.ghi" not in result
    assert "secretpass" not in result
    assert "[REDACTED]" in result


def test_redact_tokens_and_oauth_codes_in_request_urls():
    message = (
        "GET /verify-email?token=verify-canary&next=/app "
        "/oauth/callback?code=oauth-canary&state=state-canary"
    )
    result = redact_text(message)
    assert "verify-canary" not in result
    assert "oauth-canary" not in result
    assert "state-canary" not in result


def test_sensitive_structured_fields_are_redacted_by_key():
    data = {
        "Authorization": "raw-token-value",
        "headers": {"Cookie": "session=raw-cookie-value"},
        "safe_label": "campaign-42",
    }
    result = _safe(data)
    assert result["Authorization"] == "[REDACTED]"
    assert result["headers"]["Cookie"] == "[REDACTED]"
    assert result["safe_label"] == "campaign-42"
    assert "raw-token-value" not in repr(result)
    assert "raw-cookie-value" not in repr(result)


def test_log_record_redacts_message_and_drops_exception_traceback(caplog):
    install_secret_redaction()
    logger = logging.getLogger("security.secret-redaction-test")
    with caplog.at_level(logging.ERROR):
        try:
            raise RuntimeError("provider failed with password=canary-secret")
        except RuntimeError:
            logger.exception("request failed token=canary-token")

    output = caplog.text
    assert "canary-secret" not in output
    assert "canary-token" not in output
    assert "traceback_redacted" in output


def test_redact_json_string_fields_in_log_messages():
    message = '{"password":"json-canary","api_key":"key-canary","safe":"campaign-42"}'
    result = redact_text(message)
    assert "json-canary" not in result
    assert "key-canary" not in result
    assert "campaign-42" in result
