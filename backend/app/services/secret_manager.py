"""Fail-closed contract for external secret storage.

Production provider credentials must be handled by a deployment-approved secret manager.
This module deliberately ships no database, filesystem, or environment-variable fallback.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

_REFERENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,499}$")


class SecretManagerError(RuntimeError):
    """Base class for secret-storage failures safe to expose as generic errors."""


class SecretManagerUnavailable(SecretManagerError):
    """No approved secret manager is configured or reachable."""


class InvalidSecretReference(SecretManagerError):
    """A secret reference is malformed or unsafe to persist."""


def validate_secret_reference(reference: str) -> str:
    """Accept opaque identifiers only; reject inline values and URL-like userinfo."""
    if not isinstance(reference, str):
        raise InvalidSecretReference("invalid_secret_reference")
    value = reference.strip()
    if not _REFERENCE_RE.fullmatch(value):
        raise InvalidSecretReference("invalid_secret_reference")
    lowered = value.lower()
    if any(marker in lowered for marker in ("password=", "token=", "secret=", "://")):
        raise InvalidSecretReference("invalid_secret_reference")
    if any(part in {".", ".."} for part in value.replace(":", "/").split("/")):
        raise InvalidSecretReference("invalid_secret_reference")
    return value


@runtime_checkable
class SecretManager(Protocol):
    """Adapter contract; implementations must encrypt at rest and never log values."""

    async def put(self, *, purpose: str, value: str) -> str:
        """Persist a secret and return an opaque reference, never the secret itself."""
        ...

    async def get(self, *, reference: str, purpose: str) -> str:
        """Retrieve a secret only for its intended purpose."""
        ...

    async def delete(self, *, reference: str, purpose: str) -> None:
        """Idempotently delete a secret or raise a generic SecretManagerError."""
        ...


class UnconfiguredSecretManager:
    """Default adapter: fail closed until an approved backend is explicitly wired."""

    async def put(self, *, purpose: str, value: str) -> str:
        raise SecretManagerUnavailable("secret_manager_not_configured")

    async def get(self, *, reference: str, purpose: str) -> str:
        raise SecretManagerUnavailable("secret_manager_not_configured")

    async def delete(self, *, reference: str, purpose: str) -> None:
        raise SecretManagerUnavailable("secret_manager_not_configured")
