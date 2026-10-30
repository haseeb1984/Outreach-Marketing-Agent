from __future__ import annotations

import asyncio
import httpx
import pytest

from app.services.whatsapp_meta_sender import (
    MetaSendRejected, MetaSendUncertain, MetaWhatsAppSender,
    build_template_payload, build_text_payload,
)


def test_text_payload_normalizes_recipient_and_disables_link_preview():
    payload = build_text_payload(recipient="14155550123", body="Hello")
    assert payload["to"] == "14155550123"
    assert payload["text"] == {"preview_url": False, "body": "Hello"}


def test_text_payload_rejects_empty_body():
    with pytest.raises(ValueError, match="whatsapp_text_body_invalid"):
        build_text_payload(recipient="14155550123", body="  ")


def test_text_payload_rejects_oversized_body():
    with pytest.raises(ValueError, match="whatsapp_text_body_invalid"):
        build_text_payload(recipient="14155550123", body="x" * 4097)


def test_template_payload_has_provider_language_shape():
    payload = build_template_payload(recipient="14155550123", template_name="welcome", language_code="en_US")
    assert payload["template"] == {"name": "welcome", "language": {"code": "en_US"}}


def test_template_payload_rejects_invalid_language():
    with pytest.raises(ValueError, match="whatsapp_template_language_invalid"):
        build_template_payload(recipient="14155550123", template_name="welcome", language_code="bad language")


def test_sender_accepts_provider_message_id():
    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, json={"messages": [{"id": "wamid.test-123"}]},
        ))
        async with httpx.AsyncClient(transport=transport) as client:
            result = await MetaWhatsAppSender(client).send(
                version="v23.0", phone_number_id="123456789", access_token="token",
                recipient="+1 (415) 555-0123", body="Hello",
            )
        assert result == {"status": "sent", "provider_message_id": "wamid.test-123"}
    asyncio.run(scenario())


def test_sender_rejects_invalid_graph_version_before_network():
    with pytest.raises(ValueError, match="meta_graph_api_version_invalid"):
        asyncio.run(MetaWhatsAppSender().send(
            version="23", phone_number_id="123456789", access_token="token",
            recipient="14155550123", body="Hello",
        ))


def test_sender_requires_exactly_one_message_type():
    with pytest.raises(ValueError, match="exactly_one_whatsapp_message_type_required"):
        asyncio.run(MetaWhatsAppSender().send(
            version="v23.0", phone_number_id="123456789", access_token="token",
            recipient="14155550123", body="Hello", template_name="welcome", language_code="en",
        ))


def test_sender_classifies_provider_4xx_as_definite_rejection():
    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(400, json={"error": {"message": "private"}}))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(MetaSendRejected, match="meta_provider_rejected_request"):
                await MetaWhatsAppSender(client).send(
                    version="v23.0", phone_number_id="123456789", access_token="secret-token",
                    recipient="14155550123", body="Hello",
                )
    asyncio.run(scenario())


def test_sender_classifies_5xx_as_uncertain_not_retryable():
    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(500, json={"error": {"message": "private"}}))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(MetaSendUncertain, match="meta_provider_outcome_uncertain"):
                await MetaWhatsAppSender(client).send(
                    version="v23.0", phone_number_id="123456789", access_token="secret-token",
                    recipient="14155550123", body="Hello",
                )
    asyncio.run(scenario())


def test_sender_classifies_timeout_as_uncertain():
    def handler(request):
        raise httpx.ReadTimeout("simulated timeout")
    async def scenario():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(MetaSendUncertain, match="meta_transport_outcome_uncertain"):
                await MetaWhatsAppSender(client).send(
                    version="v23.0", phone_number_id="123456789", access_token="secret-token",
                    recipient="14155550123", body="Hello",
                )
    asyncio.run(scenario())


def test_sender_does_not_accept_success_without_message_id():
    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"messages": []}))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(MetaSendUncertain, match="meta_success_response_missing_message_id"):
                await MetaWhatsAppSender(client).send(
                    version="v23.0", phone_number_id="123456789", access_token="secret-token",
                    recipient="14155550123", body="Hello",
                )
    asyncio.run(scenario())


def test_sender_does_not_follow_redirects_in_injected_client_or_leak_provider_body():
    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={"Location": "https://evil.test"}))
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            with pytest.raises(MetaSendRejected) as error:
                await MetaWhatsAppSender(client).send(
                    version="v23.0", phone_number_id="123456789", access_token="secret-token",
                    recipient="14155550123", body="Hello",
                )
        assert "evil" not in str(error.value)
        assert "secret-token" not in str(error.value)
    asyncio.run(scenario())



def test_payload_builders_normalize_formatted_phone_numbers():
    assert build_text_payload(recipient="+1 (415) 555-0123", body="Hello")["to"] == "14155550123"
    assert build_template_payload(
        recipient="+1-415-555-0123", template_name="welcome", language_code="en_US",
    )["to"] == "14155550123"


@pytest.mark.parametrize("recipient", ["abc14155550123", "14155550123xyz", "++14155550123", "1+4155550123", "123", ""])
def test_payload_builders_reject_malformed_phone_numbers(recipient):
    with pytest.raises(ValueError, match="whatsapp_recipient_invalid"):
        build_text_payload(recipient=recipient, body="Hello")
