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


def _dispatch_fakes(monkeypatch, *, queue_result=True, policy_result=None, queue_error=False):
    from uuid import uuid4

    monkeypatch.setattr(settings, "whatsapp_dispatch_enabled", True)
    monkeypatch.setenv("WHATSAPP_DISPATCH_ENABLED", "true")

    class Connection:
        async def fetchrow(self, query, *args):
            return {"body": "Approved outreach", "contact_phone_e164": "+14155550123"}

    class Pool:
        def acquire(self):
            from contextlib import asynccontextmanager
            @asynccontextmanager
            async def connection():
                yield Connection()
            return connection()

    class Queue:
        def __init__(self):
            self.finished = []
        async def finish_claim(self, **kwargs):
            self.finished.append(kwargs)
            if queue_error:
                raise RuntimeError("simulated queue persistence outage")
            return queue_result

    class Subscriptions:
        def __init__(self):
            self.finished = []
        async def validate_job_reservation(self, **kwargs):
            return {"allowed": True, "reservation_status": "reserved"}
        async def finish_reservation(self, **kwargs):
            self.finished.append(kwargs)
            return True

    class Credentials:
        async def get_active_credentials(self, **kwargs):
            return type("Credential", (), {
                "phone_number_id": "12345678901", "access_token": "test-token"
            })()

    class Policy:
        def __init__(self, pool):
            pass
        async def evaluate(self, **kwargs):
            return policy_result or {"allowed": True, "requires_approved_template": False}

    monkeypatch.setattr(worker, "WhatsAppCredentialStore", lambda pool: Credentials())
    monkeypatch.setattr(worker, "WhatsAppSendPolicy", Policy)

    delivery = {
        "id": str(uuid4()), "workspace_id": "workspace-a",
        "lease_token": str(uuid4()), "usage_reservation_id": str(uuid4()),
        "draft_id": str(uuid4()), "prospect_id": str(uuid4()),
        "account_id": str(uuid4()),
    }
    return Pool(), Queue(), Subscriptions(), delivery


def test_uncertain_meta_outcome_is_terminal_and_consumes_reserved_usage(monkeypatch):
    from app.services.whatsapp_meta_sender import MetaSendUncertain

    pool, queue, subscriptions, delivery = _dispatch_fakes(monkeypatch)

    class Sender:
        def __init__(self):
            self.calls = 0
        async def send(self, **kwargs):
            self.calls += 1
            raise MetaSendUncertain("meta_transport_outcome_uncertain")

    sender = Sender()
    result = asyncio.run(worker.process_claimed_delivery(
        pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery, sender=sender,
    ))

    assert result == "provider_uncertain"
    assert sender.calls == 1
    assert queue.finished[0]["outcome"] == "uncertain"
    assert subscriptions.finished == [{
        "workspace_id": "workspace-a",
        "reservation_id": delivery["usage_reservation_id"],
        "outcome": "consumed",
    }]


def test_definite_meta_rejection_releases_reserved_usage(monkeypatch):
    from app.services.whatsapp_meta_sender import MetaSendRejected

    pool, queue, subscriptions, delivery = _dispatch_fakes(monkeypatch)

    class Sender:
        async def send(self, **kwargs):
            raise MetaSendRejected("meta_request_rejected")

    result = asyncio.run(worker.process_claimed_delivery(
        pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery, sender=Sender(),
    ))

    assert result == "provider_rejected"
    assert queue.finished[0]["outcome"] == "failed"
    assert subscriptions.finished[0]["outcome"] == "released"


def test_confirmed_provider_send_consumes_usage_even_if_lease_completion_loses(monkeypatch):
    pool, queue, subscriptions, delivery = _dispatch_fakes(monkeypatch, queue_result=False)

    class Sender:
        async def send(self, **kwargs):
            return {"provider_message_id": "wamid.test-confirmed"}

    result = asyncio.run(worker.process_claimed_delivery(
        pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery, sender=Sender(),
    ))

    assert result == "sent_lease_completion_lost"
    assert queue.finished[0]["outcome"] == "sent"
    assert queue.finished[0]["provider_message_id"] == "wamid.test-confirmed"
    assert subscriptions.finished[0]["outcome"] == "consumed"


def test_confirmed_provider_send_consumes_usage_when_queue_persistence_raises(monkeypatch):
    pool, queue, subscriptions, delivery = _dispatch_fakes(monkeypatch, queue_error=True)

    class Sender:
        async def send(self, **kwargs):
            return {"provider_message_id": "wamid.confirmed-db-outage"}

    result = asyncio.run(worker.process_claimed_delivery(
        pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery, sender=Sender(),
    ))

    assert result == "sent_lease_completion_lost"
    assert queue.finished[0]["outcome"] == "sent"
    assert subscriptions.finished[0]["outcome"] == "consumed"


def test_uncertain_provider_outcome_consumes_usage_when_queue_persistence_raises(monkeypatch):
    from app.services.whatsapp_meta_sender import MetaSendUncertain

    pool, queue, subscriptions, delivery = _dispatch_fakes(monkeypatch, queue_error=True)

    class Sender:
        async def send(self, **kwargs):
            raise MetaSendUncertain("meta_transport_outcome_uncertain")

    result = asyncio.run(worker.process_claimed_delivery(
        pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery, sender=Sender(),
    ))

    assert result == "provider_uncertain"
    assert queue.finished[0]["outcome"] == "uncertain"
    assert subscriptions.finished[0]["outcome"] == "consumed"


def test_definite_provider_rejection_releases_usage_when_queue_persistence_raises(monkeypatch):
    from app.services.whatsapp_meta_sender import MetaSendRejected

    pool, queue, subscriptions, delivery = _dispatch_fakes(monkeypatch, queue_error=True)

    class Sender:
        async def send(self, **kwargs):
            raise MetaSendRejected("meta_request_rejected")

    result = asyncio.run(worker.process_claimed_delivery(
        pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery, sender=Sender(),
    ))

    assert result == "provider_rejected"
    assert queue.finished[0]["outcome"] == "failed"
    assert subscriptions.finished[0]["outcome"] == "released"


@pytest.mark.parametrize("failure", ["entitlement", "policy", "preflight"])
def test_pre_provider_failure_releases_usage_when_queue_persistence_raises(monkeypatch, failure):
    pool, queue, subscriptions, delivery = _dispatch_fakes(monkeypatch, queue_error=True)
    if failure == "entitlement":
        async def denied(**kwargs):
            return {"allowed": False, "reason": "subscription_inactive", "reservation_status": "reserved"}
        subscriptions.validate_job_reservation = denied
    elif failure == "policy":
        class DeniedPolicy:
            def __init__(self, pool): pass
            async def evaluate(self, **kwargs):
                return {"allowed": False, "reason": "contact_suppressed"}
        monkeypatch.setattr(worker, "WhatsAppSendPolicy", DeniedPolicy)
    else:
        class BrokenCredentials:
            async def get_active_credentials(self, **kwargs):
                raise RuntimeError("credential store unavailable")
        monkeypatch.setattr(worker, "WhatsAppCredentialStore", lambda pool: BrokenCredentials())
    class ForbiddenSender:
        async def send(self, **kwargs):
            raise AssertionError("pre-provider failure must not call Meta")
    result = asyncio.run(worker.process_claimed_delivery(
        pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery,
        sender=ForbiddenSender(),
    ))
    expected = {"entitlement": "entitlement_denied", "policy": "policy_denied", "preflight": "preflight_failed"}[failure]
    assert result == expected
    assert queue.finished[0]["outcome"] == "failed"
    assert subscriptions.finished == [{
        "workspace_id": "workspace-a", "reservation_id": delivery["usage_reservation_id"],
        "outcome": "released",
    }]



def test_dispatch_uses_policy_verified_template_identity_not_queue_metadata(monkeypatch):
    approved = {
        "allowed": True,
        "requires_approved_template": True,
        "template_id": "verified-row-id",
        "provider_template_id": "meta-template-987",
        "template_name": "canonical_approved_notice",
        "language_code": "en_US",
    }
    pool, queue, subscriptions, delivery = _dispatch_fakes(
        monkeypatch, policy_result=approved,
    )
    delivery["template_name"] = "tampered_queue_template"
    delivery["language_code"] = "xx"

    class Sender:
        def __init__(self):
            self.kwargs = None
        async def send(self, **kwargs):
            self.kwargs = kwargs
            return {"provider_message_id": "wamid.template-verified"}

    sender = Sender()
    result = asyncio.run(worker.process_claimed_delivery(
        pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery, sender=sender,
    ))
    assert result == "sent"
    assert sender.kwargs["template_name"] == "canonical_approved_notice"
    assert sender.kwargs["language_code"] == "en_US"


def test_dispatch_fails_closed_when_approved_template_identity_is_incomplete(monkeypatch):
    pool, queue, subscriptions, delivery = _dispatch_fakes(
        monkeypatch,
        policy_result={
            "allowed": True,
            "requires_approved_template": True,
            "template_name": "unverified",
            "language_code": "en",
        },
    )

    class ForbiddenSender:
        async def send(self, **kwargs):
            raise AssertionError("incomplete template identity must never reach Meta")

    result = asyncio.run(worker.process_claimed_delivery(
        pool=pool, queue=queue, subscriptions=subscriptions, delivery=delivery,
        sender=ForbiddenSender(),
    ))
    assert result == "preflight_failed"
    assert queue.finished[0]["outcome"] == "failed"
    assert subscriptions.finished[0]["outcome"] == "released"
