import asyncio

from app.services.domain_verification_service import DomainVerificationService


class FakeStore:
    def __init__(self, result=None):
        self.result = result or {"verified": True, "reason": "dns_txt_token_matched"}
        self.lookup_args = None
        self.verify_args = None

    async def get_pending_challenge(self, *, workspace_id, domain):
        self.lookup_args = (workspace_id, domain)
        return {"workspace_id": workspace_id, "domain": domain, "status": "pending"}

    async def verify_challenge(self, *, workspace_id, domain, txt_values):
        self.verify_args = (workspace_id, domain, txt_values)
        return self.result


def test_verification_resolves_server_side_txt_name_and_uses_store():
    store = FakeStore()
    queried = []

    async def lookup(name):
        queried.append(name)
        return ["unrelated=value", "outreach-marketing-agent-verification=secret"]

    service = DomainVerificationService(store, txt_lookup=lookup)
    result = asyncio.run(service.verify_domain(
        workspace_id="ws-1", domain="Example.com."
    ))
    assert result["verified"] is True
    assert queried == ["_oma-verify.example.com"]
    assert store.lookup_args == ("ws-1", "example.com")
    assert store.verify_args == (
        "ws-1", "example.com",
        ["unrelated=value", "outreach-marketing-agent-verification=secret"],
    )


def test_verification_fails_closed_when_no_pending_challenge_exists():
    class MissingChallengeStore(FakeStore):
        async def get_pending_challenge(self, *, workspace_id, domain):
            return None

    called = False

    async def lookup(name):
        nonlocal called
        called = True
        return []

    service = DomainVerificationService(MissingChallengeStore(), txt_lookup=lookup)
    result = asyncio.run(service.verify_domain(
        workspace_id="ws-1", domain="example.com"
    ))
    assert result == {"verified": False, "reason": "pending_challenge_not_found"}
    assert called is False


def test_verification_fails_closed_when_dns_lookup_times_out_or_fails():
    async def lookup(name):
        raise OSError("resolver unavailable")

    service = DomainVerificationService(FakeStore(), txt_lookup=lookup)
    result = asyncio.run(service.verify_domain(
        workspace_id="ws-1", domain="example.com"
    ))
    assert result == {"verified": False, "reason": "dns_lookup_failed"}
