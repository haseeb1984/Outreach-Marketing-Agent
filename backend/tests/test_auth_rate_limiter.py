import pytest

from app.services.auth_rate_limiter import AuthRateLimiter, RateLimitConfigurationError


def test_rate_limiter_requires_a_long_environment_secret():
    with pytest.raises(RateLimitConfigurationError):
        AuthRateLimiter(None, secret_key="too-short")


def test_rate_limit_digest_is_keyed_and_does_not_contain_identifier():
    limiter = AuthRateLimiter(None, secret_key="s" * 40)
    digest = limiter._digest(namespace="login:email", identifier="Private.User@example.com")
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)
    assert "private" not in digest
    assert "example.com" not in digest


def test_rate_limit_digest_is_stable_case_insensitively_and_namespaced():
    limiter = AuthRateLimiter(None, secret_key="s" * 40)
    first = limiter._digest(namespace="login:email", identifier="Person@example.com")
    second = limiter._digest(namespace="login:email", identifier=" person@EXAMPLE.com ")
    other = limiter._digest(namespace="register:email", identifier="Person@example.com")
    assert first == second
    assert first != other


def test_rate_limit_input_bounds_are_checked_before_database_access():
    import asyncio
    limiter = AuthRateLimiter(None, secret_key="s" * 40)
    cases = [
        {"namespace": "", "identifier": "person@example.com", "limit": 5, "window_seconds": 60},
        {"namespace": "login", "identifier": "", "limit": 5, "window_seconds": 60},
        {"namespace": "login", "identifier": "person@example.com", "limit": 0, "window_seconds": 60},
        {"namespace": "login", "identifier": "person@example.com", "limit": 5, "window_seconds": 0},
    ]
    for kwargs in cases:
        with pytest.raises(ValueError):
            asyncio.run(limiter.consume(**kwargs))


def test_invalid_rate_limit_does_not_touch_database():
    import asyncio
    limiter = AuthRateLimiter(None, secret_key="s" * 40)
    with pytest.raises(ValueError, match="invalid_rate_limit"):
        asyncio.run(limiter.consume(namespace="login", identifier="person@example.com", limit=-1, window_seconds=60))

class _FakeConnection:
    def __init__(self):
        self.args = None

    async def fetchrow(self, query, *args):
        self.args = args
        return {"attempts": 3, "window_started_at": args[1]}


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self):
        self.connection = _FakeConnection()

    def acquire(self):
        return _Acquire(self.connection)


def test_consume_persists_only_keyed_identifier_and_returns_limit_state():
    import asyncio

    pool = _FakePool()
    limiter = AuthRateLimiter(pool, secret_key="s" * 40)
    result = asyncio.run(limiter.consume(
        namespace="login:email",
        identifier="Private.User@example.com",
        limit=2,
        window_seconds=60,
    ))

    digest, started_at, window_seconds = pool.connection.args
    assert len(digest) == 64
    assert "private" not in digest
    assert "example.com" not in digest
    assert "Private.User@example.com" not in pool.connection.args
    assert window_seconds == 60
    assert result["allowed"] is False
    assert result["remaining"] == 0
    assert result["reset_at"] > started_at
