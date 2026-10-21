from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass

import pytest

from app.services.provider_oauth_adapter import (
    OAuthProviderConfig,
    ProviderOAuthAdapterRegistry,
    ValidatedProviderIdentity,
)
from app.services.secret_manager import SecretManagerUnavailable
from app.services.workspace_provider_oauth_callback import (
    ProviderOAuthCallbackError,
    WorkspaceProviderOAuthCallbackService,
)


STATE = "S" * 43
NONCE = "N" * 43
REDIRECT = "https://app.example.test/oauth/email/callback"
NONCE_DIGEST = hashlib.sha256(NONCE.encode()).hexdigest()


class FakeTransactionStore:
    def __init__(self, transaction=None):
        self.transaction = transaction or {
            "id": "tx-1",
            "workspace_id": "workspace-1",
            "connection_id": "connection-1",
            "user_id": "user-1",
            "provider": "email",
            "redirect_uri": REDIRECT,
            "verifier_secret_reference": "vault-prod:oauth/verifier-123",
            "nonce_sha256": NONCE_DIGEST,
        }
        self.consumed_states = []

    async def consume(self, *, state):
        self.consumed_states.append(state)
        return self.transaction


class FakeSecretManager:
    def __init__(self):
        self.deleted = []

    async def get(self, *, reference, purpose):
        assert reference == "vault-prod:oauth/verifier-123"
        assert purpose == "provider-oauth-pkce:email:connection-1"
        return "V" * 64

    async def delete(self, *, reference, purpose):
        self.deleted.append((reference, purpose))


@dataclass
class FakeAdapter:
    config: OAuthProviderConfig
    identity: ValidatedProviderIdentity

    async def build_authorization_url(self, **kwargs):
        raise NotImplementedError

    async def exchange_and_validate(self, **kwargs):
        assert kwargs["redirect_uri"] == REDIRECT
        assert kwargs["pkce_verifier"] == "V" * 64
        assert kwargs["expected_nonce_sha256"] == NONCE_DIGEST
        return self.identity


def _service(*, scopes=frozenset({"profile"}), nonce=NONCE, secret_manager=None):
    config = OAuthProviderConfig(
        provider_id="email",
        authorization_endpoint="https://provider.example.test/authorize",
        token_endpoint="https://provider.example.test/token",
        client_id="client-test",
        redirect_uris=(REDIRECT,),
        allowed_scopes=frozenset({"profile", "contacts.read"}),
    )
    adapter = FakeAdapter(
        config=config,
        identity=ValidatedProviderIdentity(
            provider_account_id="provider-account-1",
            granted_scopes=scopes,
            nonce=nonce,
        ),
    )
    store = FakeTransactionStore()
    service = WorkspaceProviderOAuthCallbackService(
        transaction_store=store,
        adapter_registry=ProviderOAuthAdapterRegistry((adapter,)),
        secret_manager=secret_manager or FakeSecretManager(),
    )
    return service, store


def test_callback_returns_only_verified_identity_metadata():
    service, store = _service()
    result = asyncio.run(service.complete(state=STATE, code="provider-code-123"))
    assert result.provider == "email"
    assert result.provider_account_id == "provider-account-1"
    assert result.granted_scopes == ("profile",)
    assert store.consumed_states == [STATE]
    assert service._secrets.deleted == [(
        "vault-prod:oauth/verifier-123",
        "provider-oauth-pkce:email:connection-1",
    )]


def test_callback_consumes_transaction_before_processing_provider_denial():
    service, store = _service()
    with pytest.raises(ProviderOAuthCallbackError, match="provider_authorization_denied"):
        asyncio.run(service.complete(state=STATE, code=None, error="access_denied"))
    assert store.consumed_states == [STATE]


def test_callback_rejects_nonce_mismatch_after_exchange():
    service, _ = _service(nonce="X" * 43)
    with pytest.raises(ProviderOAuthCallbackError, match="oauth_nonce_mismatch"):
        asyncio.run(service.complete(state=STATE, code="provider-code-123"))


def test_callback_rejects_scopes_outside_provider_allowlist():
    service, _ = _service(scopes=frozenset({"profile", "admin.full_access"}))
    with pytest.raises(ProviderOAuthCallbackError, match="oauth_scopes_exceed_allowlist"):
        asyncio.run(service.complete(state=STATE, code="provider-code-123"))


class UnavailableSecrets:
    async def get(self, *, reference, purpose):
        raise SecretManagerUnavailable("secret_manager_not_configured")


def test_callback_fails_closed_if_secret_manager_is_unavailable():
    service, _ = _service(secret_manager=UnavailableSecrets())
    with pytest.raises(ProviderOAuthCallbackError, match="oauth_provider_validation_failed"):
        asyncio.run(service.complete(state=STATE, code="provider-code-123"))


def test_malformed_state_is_rejected_without_consuming_transaction():
    service, store = _service()
    with pytest.raises(ProviderOAuthCallbackError, match="invalid_oauth_state"):
        asyncio.run(service.complete(state="bad", code="provider-code-123"))
    assert store.consumed_states == []
