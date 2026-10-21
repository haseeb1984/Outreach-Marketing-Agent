import pytest

from app.services.provider_oauth_adapter import (
    OAuthProviderConfig,
    ProviderAdapterConfigurationError,
    ProviderAdapterUnavailable,
    ProviderOAuthAdapterRegistry,
)


class FakeAdapter:
    def __init__(self, config):
        self._config = config

    @property
    def config(self):
        return self._config


def valid_config(**overrides):
    values = {
        "provider_id": "email_example",
        "authorization_endpoint": "https://auth.example.test/oauth/authorize",
        "token_endpoint": "https://auth.example.test/oauth/token",
        "client_id": "configured-client-id",
        "redirect_uris": ("https://app.example.test/oauth/email/callback",),
        "allowed_scopes": frozenset({"profile.read", "email.send"}),
        "issuer": "https://auth.example.test/",
        "audience": "configured-client-id",
    }
    values.update(overrides)
    return OAuthProviderConfig(**values)


def test_valid_provider_configuration_is_accepted():
    config = valid_config()
    assert config.validate() is config


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider_id": "Bad Provider"},
        {"client_id": ""},
        {"authorization_endpoint": "http://auth.example.test/authorize"},
        {"token_endpoint": "https://user:password@auth.example.test/token"},
        {"token_endpoint": "https://auth.example.test:bad/token"},
        {"redirect_uris": ("http://app.example.test/callback",)},
        {"redirect_uris": ("https://app.example.test/callback", "https://app.example.test/callback")},
        {"allowed_scopes": frozenset()},
        {"allowed_scopes": frozenset({"email.send?admin=true"})},
        {"issuer": "http://auth.example.test/"},
        {"audience": " "},
    ],
)
def test_invalid_provider_configuration_is_rejected(overrides):
    with pytest.raises(ProviderAdapterConfigurationError):
        valid_config(**overrides).validate()


def test_registry_fails_closed_when_no_provider_is_configured():
    registry = ProviderOAuthAdapterRegistry()
    assert registry.configured_provider_ids() == ()
    with pytest.raises(ProviderAdapterUnavailable, match="provider_oauth_adapter_not_configured"):
        registry.get("email_example")


def test_registry_only_exposes_explicitly_registered_valid_adapters():
    config = valid_config()
    registry = ProviderOAuthAdapterRegistry((FakeAdapter(config),))
    assert registry.configured_provider_ids() == ("email_example",)
    assert registry.get("email_example").config is config
    with pytest.raises(ProviderAdapterUnavailable):
        registry.get("whatsapp_example")


def test_registry_rejects_duplicate_provider_ids():
    config = valid_config()
    with pytest.raises(ProviderAdapterConfigurationError, match="duplicate_provider_adapter"):
        ProviderOAuthAdapterRegistry((FakeAdapter(config), FakeAdapter(config)))
