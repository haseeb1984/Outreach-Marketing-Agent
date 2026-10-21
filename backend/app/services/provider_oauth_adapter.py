"""Provider OAuth adapter contract and fail-closed registry.

Concrete provider integrations must implement this contract and pass provider sandbox
verification before being registered in production. This module performs no network I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from app.services.provider_oauth_security import ProviderOAuthSecurityError, validate_redirect_uri

_PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")
_SCOPE_RE = re.compile(r"^[A-Za-z0-9:._/-]{1,120}$")


class ProviderAdapterUnavailable(RuntimeError):
    """Provider has no explicitly configured and approved OAuth adapter."""


class ProviderAdapterConfigurationError(ValueError):
    """Adapter configuration is malformed or violates the deployment policy."""


@dataclass(frozen=True)
class OAuthProviderConfig:
    provider_id: str
    authorization_endpoint: str
    token_endpoint: str
    client_id: str
    redirect_uris: tuple[str, ...]
    allowed_scopes: frozenset[str]
    issuer: str | None = None
    audience: str | None = None

    def validate(self) -> "OAuthProviderConfig":
        if not isinstance(self.provider_id, str) or not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise ProviderAdapterConfigurationError("invalid_provider_id")
        if not isinstance(self.client_id, str) or not self.client_id.strip() or len(self.client_id) > 512:
            raise ProviderAdapterConfigurationError("invalid_client_id")
        if not self.redirect_uris or len(set(self.redirect_uris)) != len(self.redirect_uris):
            raise ProviderAdapterConfigurationError("invalid_redirect_uri_allowlist")
        for redirect_uri in self.redirect_uris:
            try:
                validate_redirect_uri(redirect_uri, allowed_uris=self.redirect_uris)
            except ProviderOAuthSecurityError as exc:
                raise ProviderAdapterConfigurationError("invalid_redirect_uri_allowlist") from exc
        for endpoint in (self.authorization_endpoint, self.token_endpoint):
            parsed = urlsplit(endpoint) if isinstance(endpoint, str) else None
            if (parsed is None or parsed.scheme != "https" or not parsed.hostname
                    or parsed.username or parsed.password or parsed.fragment
                    or any(char.isspace() for char in endpoint)):
                raise ProviderAdapterConfigurationError("invalid_provider_endpoint")
            try:
                parsed.port
            except ValueError as exc:
                raise ProviderAdapterConfigurationError("invalid_provider_endpoint") from exc
        if not self.allowed_scopes or any(
            not isinstance(scope, str) or not _SCOPE_RE.fullmatch(scope)
            for scope in self.allowed_scopes
        ):
            raise ProviderAdapterConfigurationError("invalid_allowed_scopes")
        if self.issuer is not None and (not self.issuer.startswith("https://") or len(self.issuer) > 2048):
            raise ProviderAdapterConfigurationError("invalid_issuer")
        if self.audience is not None and (not self.audience.strip() or len(self.audience) > 512):
            raise ProviderAdapterConfigurationError("invalid_audience")
        return self


@dataclass(frozen=True)
class AuthorizationRequest:
    url: str
    state: str
    pkce_challenge: str
    redirect_uri: str
    requested_scopes: tuple[str, ...]


@dataclass(frozen=True)
class ValidatedProviderIdentity:
    provider_account_id: str
    granted_scopes: frozenset[str]
    nonce: str


@runtime_checkable
class ProviderOAuthAdapter(Protocol):
    """Concrete adapters must validate issuer/audience, nonce, scopes and account identity."""

    @property
    def config(self) -> OAuthProviderConfig: ...

    async def build_authorization_url(
        self, *, state: str, pkce_challenge: str, redirect_uri: str,
        requested_scopes: tuple[str, ...], nonce: str,
    ) -> str:
        """Build URL only from validated config and server-generated values."""
        ...

    async def exchange_and_validate(
        self, *, code: str, pkce_verifier: str, redirect_uri: str,
        expected_nonce_sha256: str,
    ) -> ValidatedProviderIdentity:
        """Exchange over verified TLS; return identity with nonce for digest verification."""
        ...


class ProviderOAuthAdapterRegistry:
    """Explicit allowlist; missing or invalid provider configuration always fails closed."""

    def __init__(self, adapters: tuple[ProviderOAuthAdapter, ...] = ()) -> None:
        self._adapters: dict[str, ProviderOAuthAdapter] = {}
        for adapter in adapters:
            config = adapter.config.validate()
            if config.provider_id in self._adapters:
                raise ProviderAdapterConfigurationError("duplicate_provider_adapter")
            self._adapters[config.provider_id] = adapter

    def get(self, provider_id: str) -> ProviderOAuthAdapter:
        adapter = self._adapters.get(provider_id)
        if adapter is None:
            raise ProviderAdapterUnavailable("provider_oauth_adapter_not_configured")
        return adapter

    def configured_provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))
