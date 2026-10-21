from __future__ import annotations

import asyncio
from uuid import UUID
from urllib.parse import urlencode

import pytest

from app.services.provider_oauth_adapter import (
    OAuthProviderConfig,
    ProviderOAuthAdapterRegistry,
)
from app.services.workspace_provider_oauth_start import (
    ProviderOAuthStartError,
    WorkspaceProviderOAuthStartService,
)

REDIRECT = "https://app.example.test/oauth/email/callback"
AUTH_ENDPOINT = "https://provider.example.test/authorize"


class FakeSecrets:
    def __init__(self):
        self.values = {}
        self.deleted = []

    async def put(self, *, purpose, value):
        self.values["vault-prod:oauth/verifier-123"] = (purpose, value)
        return "vault-prod:oauth/verifier-123"

    async def get(self, *, reference, purpose):
        return self.values[reference][1]

    async def delete(self, *, reference, purpose):
        self.deleted.append((reference, purpose))
        self.values.pop(reference, None)


class FakeTransactions:
    def __init__(self):
        self.created = []

    async def create(self, **kwargs):
        assert isinstance(kwargs["connection_id"], UUID)
        assert isinstance(kwargs["user_id"], UUID)
        self.created.append(kwargs)
        return {"id": "tx-1"}


class FakeAdapter:
    def __init__(self, authorization_url=None):
        self.config = OAuthProviderConfig(
            provider_id="email",
            authorization_endpoint=AUTH_ENDPOINT,
            token_endpoint="https://provider.example.test/token",
            client_id="test-client",
            redirect_uris=(REDIRECT,),
            allowed_scopes=frozenset({"profile", "contacts.read"}),
        )
        self.authorization_url = authorization_url

    async def build_authorization_url(self, *, state, pkce_challenge, redirect_uri,
                                      requested_scopes, nonce):
        assert len(state) == 43
        assert len(nonce) == 43
        assert len(pkce_challenge) == 43
        assert redirect_uri == REDIRECT
        assert requested_scopes == ("profile",)
        return self.authorization_url or (
            f"{AUTH_ENDPOINT}?" + urlencode({
                "state": state,
                "code_challenge": pkce_challenge,
                "code_challenge_method": "S256",
                "redirect_uri": redirect_uri,
                "nonce": nonce,
                "response_type": "code",
                "scope": " ".join(requested_scopes),
            })
        )

    async def exchange_and_validate(self, **kwargs):
        raise NotImplementedError


def _service(*, authorization_url=None, scopes=("profile",)):
    adapter = FakeAdapter(authorization_url)
    transactions = FakeTransactions()
    secrets = FakeSecrets()
    service = WorkspaceProviderOAuthStartService(
        transaction_store=transactions,
        adapter_registry=ProviderOAuthAdapterRegistry((adapter,)),
        secret_manager=secrets,
        redirect_uris={"email": (REDIRECT,)},
        requested_scopes={"email": tuple(scopes)},
    )
    return service, transactions, secrets


def test_start_persists_transaction_and_returns_only_authorization_url():
    service, transactions, secrets = _service()
    result = asyncio.run(service.start(
        workspace_id="workspace-1",
        connection_id="11111111-1111-4111-8111-111111111111",
        user_id="22222222-2222-4222-8222-222222222222",
        provider="email",
    ))
    assert result.authorization_url.startswith(AUTH_ENDPOINT + "?")
    from urllib.parse import parse_qs, urlsplit
    query = parse_qs(urlsplit(result.authorization_url).query)
    assert query["state"] == [transactions.created[0]["state"]]
    assert query["code_challenge"] == [transactions.created[0]["pkce_challenge"]]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [REDIRECT]
    assert query["nonce"] == [transactions.created[0]["nonce"]]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["profile"]
    assert result.expires_in_seconds == 600
    assert len(transactions.created) == 1
    transaction = transactions.created[0]
    assert transaction["state"]
    assert transaction["nonce"]
    assert transaction["verifier_secret_reference"] == "vault-prod:oauth/verifier-123"
    assert "verifier" not in result.authorization_url.lower()
    assert secrets.deleted == []


def test_start_rejects_authorization_url_host_mismatch_and_deletes_verifier():
    service, transactions, secrets = _service(
        authorization_url="https://attacker.example.test/authorize?state=abc"
    )
    with pytest.raises(ProviderOAuthStartError, match="oauth_authorization_url_invalid"):
        asyncio.run(service.start(
            workspace_id="workspace-1",
            connection_id="11111111-1111-4111-8111-111111111111",
            user_id="22222222-2222-4222-8222-222222222222",
            provider="email",
        ))
    assert len(transactions.created) == 1
    assert len(secrets.deleted) == 1



def test_start_rejects_same_host_url_with_missing_pkce_and_nonce_parameters():
    service, transactions, secrets = _service(
        authorization_url=f"{AUTH_ENDPOINT}?state={'S' * 43}&code_challenge={'C' * 43}"
    )
    with pytest.raises(ProviderOAuthStartError, match="oauth_authorization_url_invalid"):
        asyncio.run(service.start(
            workspace_id="workspace-1",
            connection_id="11111111-1111-4111-8111-111111111111",
            user_id="22222222-2222-4222-8222-222222222222",
            provider="email",
        ))
    assert len(transactions.created) == 1
    assert len(secrets.deleted) == 1

def test_start_rejects_scopes_outside_explicit_allowlist_before_storing_secret():
    service, transactions, secrets = _service(scopes=("profile", "mail.send"))
    with pytest.raises(ProviderOAuthStartError, match="oauth_scopes_not_allowlisted"):
        asyncio.run(service.start(
            workspace_id="workspace-1",
            connection_id="11111111-1111-4111-8111-111111111111",
            user_id="22222222-2222-4222-8222-222222222222",
            provider="email",
        ))
    assert transactions.created == []
    assert secrets.values == {}
