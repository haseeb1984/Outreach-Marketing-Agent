"""Strict, no-retry Meta WhatsApp Cloud API sender adapter.

The adapter deliberately does not claim queue rows or decide eligibility. Callers must
re-evaluate WhatsAppSendPolicy immediately before use and must treat MetaSendUncertain
as terminal until provider evidence is reconciled. Production dispatch remains disabled
unless a separately reviewed worker is deployed.
"""
from __future__ import annotations

import re
from typing import Any

import httpx


class MetaSendRejected(Exception):
    """Provider definitively rejected the request before accepting the message."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class MetaSendUncertain(Exception):
    """The provider may have accepted the message; automatic retries are unsafe."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_VERSION = re.compile(r"^v[0-9]{2,3}\.0$")
_ASSET_ID = re.compile(r"^[0-9]{5,128}$")


def _normalize_recipient(recipient: str) -> str:
    """Normalize human-formatted international numbers without discarding letters."""
    if not isinstance(recipient, str) or not recipient or len(recipient) > 32:
        raise ValueError("whatsapp_recipient_invalid")
    if any(not (char.isdigit() or char in "+ ()-.") for char in recipient):
        raise ValueError("whatsapp_recipient_invalid")
    normalized = "".join(char for char in recipient if char.isdigit())
    if not 7 <= len(normalized) <= 15 or (recipient.count("+") > 1 or ("+" in recipient and not recipient.lstrip().startswith("+"))):
        raise ValueError("whatsapp_recipient_invalid")
    return normalized


def _validate_common(version: str, phone_number_id: str, access_token: str, recipient: str) -> str:
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise ValueError("meta_graph_api_version_invalid")
    if not isinstance(phone_number_id, str) or not _ASSET_ID.fullmatch(phone_number_id):
        raise ValueError("meta_phone_number_id_invalid")
    if not isinstance(access_token, str) or not access_token.strip() or any(c.isspace() for c in access_token):
        raise ValueError("meta_access_token_invalid")
    return _normalize_recipient(recipient)


def build_text_payload(*, recipient: str, body: str) -> dict[str, Any]:
    normalized = _normalize_recipient(recipient)
    if not isinstance(body, str) or not body.strip() or len(body) > 4096:
        raise ValueError("whatsapp_text_body_invalid")
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }


def build_template_payload(
    *, recipient: str, template_name: str, language_code: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_recipient(recipient)
    if not isinstance(template_name, str) or not template_name.strip() or len(template_name) > 512:
        raise ValueError("whatsapp_template_name_invalid")
    if not isinstance(language_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", language_code):
        raise ValueError("whatsapp_template_language_invalid")
    components = []
    supplied = parameters or {}
    if not isinstance(supplied, dict) or set(supplied) - {"body", "header", "buttons"}:
        raise ValueError("whatsapp_template_component_invalid")
    for component_type in ("body", "header"):
        values = supplied.get(component_type, [])
        if not isinstance(values, list) or len(values) > 20:
            raise ValueError("whatsapp_template_parameter_invalid")
        if values:
            if any(not isinstance(value, str) or not value.strip() or len(value) > 1024 for value in values):
                raise ValueError("whatsapp_template_parameter_invalid")
            components.append({
                "type": component_type,
                "parameters": [{"type": "text", "text": value} for value in values],
            })
    buttons = supplied.get("buttons", [])
    if not isinstance(buttons, list) or len(buttons) > 10:
        raise ValueError("whatsapp_template_button_parameters_invalid")
    seen_indexes: set[int] = set()
    for button in buttons:
        if not isinstance(button, dict) or set(button) != {"index", "sub_type", "value"}:
            raise ValueError("whatsapp_template_button_parameters_invalid")
        index = button.get("index")
        value = button.get("value")
        if (isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 9
            or index in seen_indexes or button.get("sub_type") != "url"
            or not isinstance(value, str) or not value.strip() or len(value) > 2000):
            raise ValueError("whatsapp_template_button_parameters_invalid")
        seen_indexes.add(index)
        components.append({
            "type": "button", "sub_type": "url", "index": str(index),
            "parameters": [{"type": "text", "text": value}],
        })
    template = {"name": template_name, "language": {"code": language_code}}
    if components:
        template["components"] = components
    return {"messaging_product": "whatsapp", "to": normalized, "type": "template", "template": template}


class MetaWhatsAppSender:
    """Single-attempt adapter. Inject an AsyncClient in tests; never logs tokens/payloads."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def send(
        self, *, version: str, phone_number_id: str, access_token: str,
        recipient: str, body: str | None = None, template_name: str | None = None,
        language_code: str | None = None,
        template_parameters: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        normalized = _validate_common(version, phone_number_id, access_token, recipient)
        if (body is None) == (template_name is None):
            raise ValueError("exactly_one_whatsapp_message_type_required")
        if body is not None:
            payload = build_text_payload(recipient=normalized, body=body)
        else:
            if language_code is None:
                raise ValueError("whatsapp_template_language_required")
            payload = build_template_payload(
                recipient=normalized, template_name=template_name or "", language_code=language_code,
                parameters=template_parameters,
            )

        url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            if self._client is not None:
                response = await self._client.post(url, json=payload, headers=headers)
            else:
                timeout = httpx.Timeout(8.0, connect=4.0)
                async with httpx.AsyncClient(
                    timeout=timeout, follow_redirects=False, trust_env=False,
                ) as client:
                    response = await client.post(url, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError):
            raise MetaSendUncertain("meta_transport_outcome_uncertain") from None
        except Exception:
            # A transport wrapper may fail after bytes were handed off. Never blind-retry.
            raise MetaSendUncertain("meta_transport_outcome_uncertain") from None

        if response.status_code in {408, 425, 429} or response.status_code >= 500:
            raise MetaSendUncertain("meta_provider_outcome_uncertain")
        if not 200 <= response.status_code < 300:
            raise MetaSendRejected("meta_provider_rejected_request")
        try:
            data = response.json()
        except (ValueError, TypeError):
            raise MetaSendUncertain("meta_success_response_unparseable") from None
        messages = data.get("messages") if isinstance(data, dict) else None
        first = messages[0] if isinstance(messages, list) and messages else None
        provider_id = first.get("id") if isinstance(first, dict) else None
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise MetaSendUncertain("meta_success_response_missing_message_id")
        return {"status": "sent", "provider_message_id": provider_id}
