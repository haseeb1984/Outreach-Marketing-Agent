"""Authorization-start orchestration for short-lived, single-use provider OAuth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from app.services.provider_oauth_adapter import (
    ProviderAdapterUnavailable,
    ProviderOAuthAdapterRegistry,
)
from app.services.provider_oauth_security import create_pkce_pair
from app.services.secret_manager import SecretManager, SecretManagerError
from app.services.workspace_provider_oauth_transaction_store import new_oauth_state


class ProviderOAuthStartError(RuntimeError):
    """Safe error code for an OAuth authorization-start failure."""


@dataclass(frozen=True)
class ProviderOAuthStart:
    authorization_url: str
    expires_in_seconds: int


class WorkspaceProviderOAuthStartService:
    """Create server-side OAuth state and PKCE material before returning a provider URL."""

    def __init__(
        self,
        *,
        transaction_store: Any,
        adapter_registry: ProviderOAuthAdapterRegistry,
        secret_manager: SecretManager,
        redirect_uris: dict[str, tuple[str, ...]],
        requested_scopes: dict[str, tuple[str, ...]],
    ) -> None:
        self._transactions = transaction_store
        self._adapters = adapter_registry
        self._secrets = secret_manager
        self._redirect_uris = redirect_uris
        self._requested_scopes = requested_scopes

    async def start(
        self, *, workspace_id: str, connection_id: str, user_id: str, provider: str,
    ) -> ProviderOAuthStart:
        reference: str | None = None
        try:
            adapter = self._adapters.get(provider)
            config = adapter.config.validate()
            if config.provider_id != provider:
                raise ProviderOAuthStartError("oauth_provider_mismatch")
            redirect_uris = self._redirect_uris.get(provider, ())
            if not redirect_uris or any(uri not in config.redirect_uris for uri in redirect_uris):
                raise ProviderOAuthStartError("oauth_redirect_uri_not_configured")
            redirect_uri = redirect_uris[0]
            scopes = self._requested_scopes.get(provider, ())
            if not scopes or len(set(scopes)) != len(scopes) or not set(scopes).issubset(config.allowed_scopes):
                raise ProviderOAuthStartError("oauth_scopes_not_allowlisted")

            verifier, challenge = create_pkce_pair()
            state = new_oauth_state()
            nonce = new_oauth_state()
            reference = await self._secrets.put(
                purpose=f"provider-oauth-pkce:{provider}:{connection_id}",
                value=verifier,
            )
            from app.services.secret_manager import validate_secret_reference
            reference = validate_secret_reference(reference)
            await self._transactions.create(
                workspace_id=workspace_id,
                connection_id=UUID(str(connection_id)),
                user_id=UUID(str(user_id)),
                provider=provider,
                state=state,
                pkce_challenge=challenge,
                verifier_secret_reference=reference,
                redirect_uri=redirect_uri,
                nonce=nonce,
                allowed_redirect_uris=config.redirect_uris,
                lifetime_seconds=600,
            )
            authorization_url = await adapter.build_authorization_url(
                state=state,
                pkce_challenge=challenge,
                redirect_uri=redirect_uri,
                requested_scopes=tuple(scopes),
                nonce=nonce,
            )
            parsed_url = urlsplit(authorization_url) if isinstance(authorization_url, str) else None
            configured = urlsplit(config.authorization_endpoint)
            if (
                parsed_url is None or parsed_url.scheme != "https" or not parsed_url.hostname
                or parsed_url.username or parsed_url.password or parsed_url.fragment
                or parsed_url.scheme != configured.scheme
                or parsed_url.hostname.lower() != (configured.hostname or "").lower()
                or parsed_url.port != configured.port
                or parsed_url.path != configured.path
            ):
                raise ProviderOAuthStartError("oauth_authorization_url_invalid")
            return ProviderOAuthStart(authorization_url=authorization_url, expires_in_seconds=600)
        except ProviderOAuthStartError:
            if reference is not None:
                try:
                    await self._secrets.delete(
                        reference=reference,
                        purpose=f"provider-oauth-pkce:{provider}:{connection_id}",
                    )
                except Exception:
                    pass
            raise
        except (ProviderAdapterUnavailable, SecretManagerError, ValueError, TypeError, KeyError):
            if reference is not None:
                try:
                    await self._secrets.delete(
                        reference=reference,
                        purpose=f"provider-oauth-pkce:{provider}:{connection_id}",
                    )
                except Exception:
                    pass
            raise ProviderOAuthStartError("oauth_authorization_start_failed") from None
        except Exception:
            if reference is not None:
                try:
                    await self._secrets.delete(
                        reference=reference,
                        purpose=f"provider-oauth-pkce:{provider}:{connection_id}",
                    )
                except Exception:
                    pass
            raise ProviderOAuthStartError("oauth_authorization_start_failed") from None
