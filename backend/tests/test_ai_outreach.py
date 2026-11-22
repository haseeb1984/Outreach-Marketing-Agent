import asyncio
import json

import pytest

from app.services.ai_outreach import AIOutreachUnavailable, generate_ai_outreach


CONTEXT = {
    "client_business": "Example Analytics",
    "client_offer": "Analytics implementation",
    "target_customer_profile": "B2B SaaS teams",
    "prospect_name": "Example Prospect",
    "fit_reason": "The prospect publishes a public analytics engineering role.",
    "verified_facts": ["The company publicly lists an analytics engineering role."],
    "evidence_url": "https://example.com/careers",
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "subject": "A practical analytics question",
                        "body": "Hello — I noticed your public analytics engineering role. Would a short discussion be useful? Reply stop if you prefer no further contact.",
                    })
                }
            }]
        }

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("provider error", request=None, response=None)

    def json(self):
        return self._payload


class FakeAsyncClient:
    response = FakeResponse()
    captured = {}

    def __init__(self, **kwargs):
        self.captured = {"client_options": kwargs}

    async def __aenter__(self):
        type(self).captured = self.captured
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        type(self).captured.update({"url": url, **kwargs})
        return type(self).response


def test_generate_ai_outreach_uses_https_and_openai_compatible_contract(monkeypatch):
    FakeAsyncClient.response = FakeResponse()
    monkeypatch.setattr("app.services.ai_outreach.httpx.AsyncClient", FakeAsyncClient)

    result = asyncio.run(generate_ai_outreach(
        api_key="test-key",
        base_url="https://api.example.test/v1",
        model="test-model",
        channel="email",
        call_to_action="Would a short call help?",
        context=CONTEXT,
    ))

    captured = FakeAsyncClient.captured
    assert captured["url"] == "https://api.example.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "test-model"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    prompt = captured["json"]["messages"][1]["content"]
    assert "UNTRUSTED INPUT DATA" in prompt
    assert "The company publicly lists an analytics engineering role." in prompt
    assert result["subject"] == "A practical analytics question"
    assert "Reply stop" in result["body"]


@pytest.mark.parametrize("base_url", [
    "http://api.example.test/v1",
    "https://user:password@api.example.test/v1",
    "not-a-url",
])
def test_generate_ai_outreach_rejects_insecure_or_invalid_provider_url(base_url):
    with pytest.raises(AIOutreachUnavailable, match="ai_provider_configuration_invalid"):
        asyncio.run(generate_ai_outreach(
            api_key="test-key",
            base_url=base_url,
            model="test-model",
            channel="email",
            call_to_action="Talk?",
            context=CONTEXT,
        ))


def test_generate_ai_outreach_requires_verified_facts():
    context = {**CONTEXT, "verified_facts": []}
    with pytest.raises(ValueError, match="verified fact"):
        asyncio.run(generate_ai_outreach(
            api_key="test-key",
            base_url="https://api.example.test/v1",
            model="test-model",
            channel="email",
            call_to_action="Talk?",
            context=context,
        ))


def test_generate_ai_outreach_rejects_invalid_provider_json(monkeypatch):
    FakeAsyncClient.response = FakeResponse(payload={
        "choices": [{"message": {"content": "not-json"}}]
    })
    monkeypatch.setattr("app.services.ai_outreach.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(AIOutreachUnavailable, match="ai_provider_unavailable"):
        asyncio.run(generate_ai_outreach(
            api_key="test-key",
            base_url="https://api.example.test/v1",
            model="test-model",
            channel="email",
            call_to_action="Talk?",
            context=CONTEXT,
        ))


def test_generate_ai_outreach_requires_email_subject_and_nonempty_body(monkeypatch):
    FakeAsyncClient.response = FakeResponse(payload={
        "choices": [{"message": {"content": json.dumps({"subject": "", "body": "Hello"})}}]
    })
    monkeypatch.setattr("app.services.ai_outreach.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(AIOutreachUnavailable, match="ai_response_invalid"):
        asyncio.run(generate_ai_outreach(
            api_key="test-key",
            base_url="https://api.example.test/v1",
            model="test-model",
            channel="email",
            call_to_action="Talk?",
            context=CONTEXT,
        ))


def test_generate_ai_outreach_whatsapp_does_not_require_subject(monkeypatch):
    FakeAsyncClient.response = FakeResponse(payload={
        "choices": [{"message": {"content": json.dumps({"subject": "", "body": "Hello"})}}]
    })
    monkeypatch.setattr("app.services.ai_outreach.httpx.AsyncClient", FakeAsyncClient)

    result = asyncio.run(generate_ai_outreach(
        api_key="test-key",
        base_url="https://api.example.test/v1",
        model="test-model",
        channel="whatsapp",
        call_to_action="Talk?",
        context=CONTEXT,
    ))
    assert result == {"subject": "", "body": "Hello"}
