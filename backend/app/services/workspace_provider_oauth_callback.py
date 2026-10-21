"""Fail-closed orchestration for a provider OAuth callback.

This service validates and consumes a transaction before touching provider credentials.
It returns verified identity metadata only; callers must still persist connection state
transactionally and must never enable sending based solely on this result.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.services.provider_oauth_adapter import (
    ProviderAdapterUnavailable,
    ProviderOAuthAdapterRegistry,
    ValidatedProviderIdentity,
)
from app.services.provider_oauth_security import (
    ProviderOAuthSecurityError,
    nonce_matches,
    validate_callback_parameters,
    validate_redirect_uri,
)
from app.services.secret_manager import (
    SecretManager,
    SecretManagerError,
    validate_secret_reference,
)


class ProviderOAuthCallbackError(RuntimeError):
    """Safe, non-sensitive failure code for an OAuth callback."""


@dataclass(frozen=True)
class VerifiedOAuthCallback:
    transaction_id: str
    workspace_id: str
    connection_id: str
    user_id: str
    provider: str
    provider_account_id: str
    granted_scopes: tuple[str, ...]


class WorkspaceProviderOAuthCallbackService:
    def __init__(
        self,
        *,
        transaction_store: Any,
        adapter_registry: ProviderOAuthAdapterRegistry,
        secret_manager: SecretManager,
    ) -> None:
        self._transactions = transaction_store
        self._adapters = adapter_registry
        self._secrets = secret_manager

    async def complete(
        self, *, state: str, code: str | None, error: str | None = None,
    ) -> VerifiedOAuthCallback:
        # Reject malformed state without database access; valid state is then consumed
        # atomically before processing either success or provider-denial callbacks.
        if not isinstance(state, str) or len(state) != 43:
            raise ProviderOAuthCallbackError("invalid_oauth_state")
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", state) is None:
            raise ProviderOAuthCallbackError("invalid_oauth_state")

        try:
            transaction = await self._transactions.consume(state=state)
        except Exception:
            raise ProviderOAuthCallbackError("oauth_transaction_unavailable") from None
        if transaction is None:
            raise ProviderOAuthCallbackError("oauth_transaction_invalid_or_expired")

        try:
            authorization_code = validate_callback_parameters(
                state=state, code=code, error=error,
            )
        except ProviderOAuthSecurityError as exc:
            raise ProviderOAuthCallbackError(str(exc)) from None

        try:
            adapter = self._adapters.get(transaction["provider"])
            config = adapter.config.validate()
            if config.provider_id != transaction["provider"]:
                raise ProviderOAuthCallbackError("oauth_provider_mismatch")
            redirect_uri = validate_redirect_uri(
                transaction["redirect_uri"], allowed_uris=config.redirect_uris,
            )
            reference = validate_secret_reference(transaction["verifier_secret_reference"])
            verifier = await self._secrets.get(
                reference=reference,
                purpose=f"provider-oauth-pkce:{transaction['provider']}:{transaction['connection_id']}",
            )
            if not isinstance(verifier, str) or not 43 <= len(verifier) <= 128:
                raise ProviderOAuthCallbackError("oauth_verifier_unavailable")
            identity = await adapter.exchange_and_validate(
                code=authorization_code,
                pkce_verifier=verifier,
                redirect_uri=redirect_uri,
                expected_nonce_sha256=transaction["nonce_sha256"],
            )
        except ProviderOAuthCallbackError:
            raise
        except (ProviderAdapterUnavailable, SecretManagerError, ValueError, TypeError):
            raise ProviderOAuthCallbackError("oauth_provider_validation_failed") from None
        except Exception:
            # Provider errors may contain URLs, response bodies, codes, or credentials.
            raise ProviderOAuthCallbackError("oauth_provider_validation_failed") from None

        if not isinstance(identity, ValidatedProviderIdentity):
            raise ProviderOAuthCallbackError("oauth_identity_invalid")
        account_id = identity.provider_account_id
        if not isinstance(account_id, str) or not account_id.strip() or len(account_id) > 512:
            raise ProviderOAuthCallbackError("oauth_identity_invalid")
        if not nonce_matches(identity.nonce, transaction["nonce_sha256"]):
            raise ProviderOAuthCallbackError("oauth_nonce_mismatch")
        scopes = identity.granted_scopes
        if not isinstance(scopes, (set, frozenset, tuple, list)) or any(
            not isinstance(scope, str) for scope in scopes
        ):
            raise ProviderOAuthCallbackError("oauth_scopes_invalid")
        granted = frozenset(scopes)
        if not granted.issubset(config.allowed_scopes):
            raise ProviderOAuthCallbackError("oauth_scopes_exceed_allowlist")

        return VerifiedOAuthCallback(
            transaction_id=str(transaction["id"]),
            workspace_id=str(transaction["workspace_id"]),
            connection_id=str(transaction["connection_id"]),
            user_id=str(transaction["user_id"]),
            provider=str(transaction["provider"]),
            provider_account_id=account_id.strip(),
            granted_scopes=tuple(sorted(granted)),
        )
