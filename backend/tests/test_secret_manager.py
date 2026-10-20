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
        "  ",
        "abc",
        "https://vault.example/secrets/123",
        "vault://secret/value",
        "access_token=actual-secret-value",
        "password=hunter2",
        "secret=credential",
        "../escape",
        "has whitespace",
        "a" * 501,
    ],
)
def test_rejects_inline_values_and_unsafe_references(reference):
    with pytest.raises(InvalidSecretReference):
        validate_secret_reference(reference)


@pytest.mark.parametrize(
    "reference",
    [
        "vault-prod:outreach/provider/email/connection-123",
        "sm://project/secret-id_123",
        "secret-manager-reference-001",
    ],
)
def test_accepts_opaque_secret_manager_references(reference):
    assert validate_secret_reference(reference) == reference


def test_unconfigured_manager_fails_closed_for_every_operation():
    async def exercise():
        manager = UnconfiguredSecretManager()
        assert isinstance(manager, SecretManager)

        with pytest.raises(SecretManagerUnavailable, match="secret_manager_not_configured"):
            await manager.put(purpose="oauth_pkce_verifier", value="never-log-this")

        with pytest.raises(SecretManagerUnavailable, match="secret_manager_not_configured"):
            await manager.get(reference="vault-prod:secret-123", purpose="oauth_pkce_verifier")

        with pytest.raises(SecretManagerUnavailable, match="secret_manager_not_configured"):
            await manager.delete(reference="vault-prod:secret-123", purpose="oauth_pkce_verifier")

    asyncio.run(exercise())
