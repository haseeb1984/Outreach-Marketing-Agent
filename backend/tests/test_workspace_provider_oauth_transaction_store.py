"""Fail-closed tests for OAuth transaction input validation before persistence."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.services.workspace_provider_oauth_transaction_store import (
    WorkspaceProviderOAuthTransactionStore,
    new_oauth_state,
)


class NoDatabasePool:
    def acquire(self):
        raise AssertionError("invalid OAuth input must be rejected before database access")


def _create_kwargs() -> dict:
    return {
        "workspace_id": "workspace-test",
        "connection_id": uuid4(),
        "user_id": uuid4(),
        "provider": "email",
        "state": new_oauth_state(),
        "pkce_challenge": "A" * 43,
        "verifier_secret_reference": "vault-prod:oauth/verifier-123",
        "redirect_uri": "https://app.example.test/oauth/email/callback",
        "allowed_redirect_uris": ("https://app.example.test/oauth/email/callback",),
        "nonce": new_oauth_state(),
    }


def test_oauth_store_rejects_redirect_uri_not_in_exact_allowlist_before_db():
    kwargs = _create_kwargs()
    kwargs["redirect_uri"] = "https://attacker.example.test/oauth/email/callback"
    store = WorkspaceProviderOAuthTransactionStore(NoDatabasePool())
    with pytest.raises(ValueError, match="invalid_redirect_uri"):
        asyncio.run(store.create(**kwargs))


@pytest.mark.parametrize("reference", [
    "access_token=supersecret-value",
    "vault://provider/secret",
    "../secret-ref",
    "short",
])
def test_oauth_store_rejects_non_opaque_verifier_references_before_db(reference):
    kwargs = _create_kwargs()
    kwargs["verifier_secret_reference"] = reference
    store = WorkspaceProviderOAuthTransactionStore(NoDatabasePool())
    with pytest.raises(ValueError, match="invalid_verifier_secret_reference"):
        asyncio.run(store.create(**kwargs))


@pytest.mark.parametrize("state", ["short", "!" * 43, "x" * 44])
def test_oauth_store_rejects_malformed_state_before_db(state):
    kwargs = _create_kwargs()
    kwargs["state"] = state
    store = WorkspaceProviderOAuthTransactionStore(NoDatabasePool())
    with pytest.raises(ValueError, match="invalid_oauth_state"):
        asyncio.run(store.create(**kwargs))


def test_oauth_store_requires_explicit_redirect_allowlist():
    kwargs = _create_kwargs()
    kwargs["allowed_redirect_uris"] = ()
    store = WorkspaceProviderOAuthTransactionStore(NoDatabasePool())
    with pytest.raises(ValueError, match="redirect_uri_allowlist_required"):
        asyncio.run(store.create(**kwargs))
