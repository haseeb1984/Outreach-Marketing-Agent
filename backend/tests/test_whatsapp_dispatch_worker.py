from __future__ import annotations

import asyncio

import pytest

from app.core.config import settings
from app.workers import whatsapp_dispatch_worker as worker


def test_dispatch_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_dispatch_enabled", False)
    monkeypatch.setenv("WHATSAPP_DISPATCH_ENABLED", "true")
    assert worker.dispatch_is_enabled() is False


@pytest.mark.parametrize("value", ["", "false", "0", "yes"])
def test_dispatch_requires_explicit_process_opt_in(monkeypatch, value):
    monkeypatch.setattr(settings, "whatsapp_dispatch_enabled", True)
    monkeypatch.setenv("WHATSAPP_DISPATCH_ENABLED", value)
    assert worker.dispatch_is_enabled() is False


def test_dispatch_requires_both_flags(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_dispatch_enabled", True)
    monkeypatch.setenv("WHATSAPP_DISPATCH_ENABLED", "true")
    assert worker.dispatch_is_enabled() is True


def test_worker_refuses_to_start_when_dispatch_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_dispatch_enabled", False)
    monkeypatch.setenv("WHATSAPP_DISPATCH_ENABLED", "true")
    with pytest.raises(RuntimeError, match="WhatsApp dispatch is disabled"):
        asyncio.run(worker.run_worker())


def test_claimed_delivery_never_touches_provider_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_dispatch_enabled", False)
    monkeypatch.setenv("WHATSAPP_DISPATCH_ENABLED", "true")

    class Forbidden:
        async def validate_job_reservation(self, **kwargs):
            raise AssertionError("quota must not be checked when dispatch is disabled")

    class ForbiddenQueue:
        async def finish_claim(self, **kwargs):
            raise AssertionError("queue must not be mutated when dispatch is disabled")

    class ForbiddenPool:
        def acquire(self):
            raise AssertionError("database must not be accessed when dispatch is disabled")

    class ForbiddenSender:
        async def send(self, **kwargs):
            raise AssertionError("provider must not be called when dispatch is disabled")

    result = asyncio.run(worker.process_claimed_delivery(
        pool=ForbiddenPool(), queue=ForbiddenQueue(), subscriptions=Forbidden(),
        delivery={"workspace_id": "w"}, sender=ForbiddenSender(),
    ))
    assert result == "dispatch_disabled"
