import asyncio

import pytest

from app.services.secret_manager import (
    InvalidSecretReference,
    SecretManager,
    SecretManagerUnavailable,
    UnconfiguredSecretManager,
    validate_secret_reference,
)


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "abc",
        "https://vault.example.test/item/123",
        "vault://item/123",
        "credential-value",
        "../escape",
        "has whitespace",
        "a" * 501,
    ],
)
def test_rejects_non_opaque_or_unsafe_references(reference):
    with pytest.raises(InvalidSecretReference):
        validate_secret_reference(reference)


def test_accepts_opaque_reference():
    reference = "vault-prod:outreach/provider/email/connection-123"
    assert validate_secret_reference(reference) == reference


def test_unconfigured_manager_fails_closed_for_every_operation():
    async def exercise():
        manager = UnconfiguredSecretManager()
        assert isinstance(manager, SecretManager)

        with pytest.raises(SecretManagerUnavailable):
            await manager.put(purpose="oauth_pkce_verifier", value="example-value")

        with pytest.raises(SecretManagerUnavailable):
            await manager.get(reference="vault-prod:secret-123", purpose="oauth_pkce_verifier")

        with pytest.raises(SecretManagerUnavailable):
            await manager.delete(reference="vault-prod:secret-123", purpose="oauth_pkce_verifier")

    asyncio.run(exercise())
