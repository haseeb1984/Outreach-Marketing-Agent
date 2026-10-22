"""Defense-in-depth redaction for application log records.

Never log secrets intentionally; this module reduces accidental exposure if a
credential is interpolated into a message or exception. It is not a substitute
for safe logging practices or provider-side log access controls.
"""
from __future__ import annotations

import logging
import re
from typing import Any

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(\\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"auth(?:orization)?|cookie|set-cookie|client[_-]?secret|webhook[_-]?secret|"
    r"database[_-]?url|smtp[_-]?(?:username|password)|token)\\b\\s*[:=]\\s*)"
    r"""("[^"]*"|'[^']*'|[^\\s,;]+)"""
)
_BEARER = re.compile(r"(?i)\\b(Bearer|Basic)\\s+[A-Za-z0-9._~+/=-]+")
_URL_CREDENTIALS = re.compile(r"(://[^:/\\s]+:)[^@/\\s]+(@)")
_SENSITIVE_KEY = re.compile(
    r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"authorization|auth|cookie|client[_-]?secret|webhook[_-]?secret|database[_-]?url|"
    r"smtp[_-]?(username|password)|token|private[_-]?key|credential)"
)


def _configured_secrets() -> tuple[str, ...]:
    try:
        from app.core.config import settings

        names = (
            "secret_key", "database_url", "smtp_password", "smtp_username",
            "paddle_api_key", "paddle_webhook_secret", "outreach_webhook_secret",
            "meta_whatsapp_access_token", "meta_whatsapp_app_secret",
            "meta_whatsapp_webhook_verify_token", "trusted_egress_proxy_url",
        )
        values = {getattr(settings, name, None) for name in names}
        return tuple(sorted((v for v in values if isinstance(v, str) and len(v) >= 4), key=len, reverse=True))
    except Exception:
        return ()


def redact_text(value: str) -> str:
    """Redact known environment secrets and common inline credential patterns."""
    for secret in _configured_secrets():
        value = value.replace(secret, "[REDACTED]")
    value = _SENSITIVE_ASSIGNMENT.sub(r"\\1[REDACTED]", value)
    value = _BEARER.sub(r"\\1 [REDACTED]", value)
    value = _URL_CREDENTIALS.sub(r"\\1[REDACTED]\\2", value)
    return value


def _safe(value: Any, *, sensitive_key: bool = False) -> Any:
    if sensitive_key:
        return "[REDACTED]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, tuple):
        return tuple(_safe(item) for item in value)
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, dict):
        return {
            redact_text(str(key)): _safe(item, sensitive_key=bool(_SENSITIVE_KEY.search(str(key))))
            for key, item in value.items()
        }
    return value


def install_secret_redaction() -> None:
    """Sanitize LogRecord messages/arguments before handlers format them."""
    current = logging.getLogRecordFactory()
    if getattr(current, "_oma_secret_redaction", False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = current(*args, **kwargs)
        record.msg = _safe(record.msg)
        record.args = _safe(record.args)
        if record.exc_info:
            exc_type = record.exc_info[0]
            record.msg = (
                f"{record.msg} [exception_type="
                f"{getattr(exc_type, '__name__', 'Exception')}; traceback_redacted]"
            )
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return record

    setattr(factory, "_oma_secret_redaction", True)
    logging.setLogRecordFactory(factory)
