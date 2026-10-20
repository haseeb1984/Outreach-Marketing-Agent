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
        "password=hunter2",
        "token=abc12345",
        "../escape-path",
        "has whitespace",
        "a" * 501,
    ],
)
def test_rejects_non_opaque_or_unsafe_references(reference):
    with pytest.raises(InvalidSecretReference):
        validate_secret_reference(reference)


def test_accepts_opaque_reference_without_normalizing_it():
    reference = "vault-prod:outreach/provider/email/connection-123"
    assert validate_secret_reference(reference) == reference


def test_rejects_non_string_references():
    for reference in (None, 123, b"vault-prod:secret-123"):
        with pytest.raises(InvalidSecretReference):
            validate_secret_reference(reference)


def test_unconfigured_manager_fails_closed_for_every_operation():
    async def exercise():
        manager = UnconfiguredSecretManager()
        assert isinstance(manager, SecretManager)

        with pytest.raises(SecretManagerUnavailable, match="secret_manager_not_configured"):
            await manager.put(purpose="oauth_pkce_verifier", value="example-value")

        with pytest.raises(SecretManagerUnavailable, match="secret_manager_not_configured"):
            await manager.get(reference="vault-prod:secret-123", purpose="oauth_pkce_verifier")

        with pytest.raises(SecretManagerUnavailable, match="secret_manager_not_configured"):
            await manager.delete(reference="vault-prod:secret-123", purpose="oauth_pkce_verifier")

    asyncio.run(exercise())
