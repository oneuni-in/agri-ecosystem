# backend/core/tests/test_rate_limit_hardening.py
"""Three ways the limiter could be walked around, and the memory it could eat.

1. ORDER. SecureRouter registered require_auth ahead of rate_limit, and
   FastAPI stops at the first failing dependency - so an unauthenticated
   request to a private route never reached the limiter and was never
   counted. Each attempt still costs a session lookup or an RS256
   verification, so it was free amplification. Public routes were always
   counted; only the private ones leaked.

2. DEGRADED MODE. When Redis is unreachable the limiter falls back to a
   per-process window. Keeping the same number there means N workers grant
   N x the limit exactly when the shared counter is gone, so the fallback
   needs its own, tighter budget.

3. UNBOUNDED FALLBACK MEMORY. That fallback dict was only ever cleared by
   reset(). One key per (ip, path) with no eviction, during an outage, on
   keys the caller chooses - a slow OOM for the price of some 404s.

The 404 half lives in test_slug_redirect_limit.py: unrouted paths never
reach a route dependency at all, so the limiter cannot see them.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from redis.exceptions import RedisError

from settings import get_settings
from shared import security
from shared.security import SecureRouter, rate_limiter


class Message(BaseModel):
    detail: str


class _DeadRedis:
    """Redis that refuses instantly.

    Pointing REDIS_URL at a closed port also reaches the fallback, but pays a
    connection timeout per call - and the eviction test makes ten thousand of
    them, which turned a two-minute file into a ten-minute one.
    """

    async def incr(self, key: str) -> int:
        raise RedisError("unreachable")

    async def expire(self, key: str, window: int) -> bool:  # pragma: no cover
        raise RedisError("unreachable")


@pytest.fixture
def redis_down(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(security, "get_redis", lambda: _DeadRedis())
    rate_limiter.reset()
    yield


def make_client() -> TestClient:
    router = SecureRouter()

    @router.get("/private")
    async def private_route() -> Message:  # pragma: no cover - auth stops it
        return Message(detail="secret")

    @router.get("/open", public=True)
    async def open_route() -> Message:
        return Message(detail="ok")

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_unauthenticated_requests_to_private_routes_are_counted(
    monkeypatch: pytest.MonkeyPatch, redis_down: None
) -> None:
    """THE fix: a 401 must still spend budget, or credential probing and the
    DB work behind it are unmetered."""
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_DEGRADED_REQUESTS", "1")  # redis is stubbed down
    get_settings.cache_clear()

    client = make_client()
    assert client.get("/private").status_code == 401
    # second identical attempt: the limiter saw the first one
    assert client.get("/private").status_code == 429


def test_public_routes_are_still_counted(monkeypatch: pytest.MonkeyPatch, redis_down: None) -> None:
    """Reordering the dependencies must not cost public routes their limit."""
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_DEGRADED_REQUESTS", "1")  # redis is stubbed down
    get_settings.cache_clear()

    client = make_client()
    assert client.get("/open").status_code == 200
    assert client.get("/open").status_code == 429


def test_authenticated_path_still_reaches_the_route(
    monkeypatch: pytest.MonkeyPatch, redis_down: None
) -> None:
    """Sanity: with budget to spare, a public route answers normally - the
    limiter running first must not swallow ordinary traffic."""
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "10")
    monkeypatch.setenv("RATE_LIMIT_DEGRADED_REQUESTS", "10")  # redis is stubbed down
    get_settings.cache_clear()

    client = make_client()
    assert client.get("/open").status_code == 200
    assert client.get("/open").json()["detail"] == "ok"


async def test_degraded_mode_uses_its_own_tighter_budget(
    monkeypatch: pytest.MonkeyPatch, redis_down: None
) -> None:
    """Redis is gone, so this window is per-process. It must not hand out the
    full shared allowance to every worker."""
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "100")
    monkeypatch.setenv("RATE_LIMIT_DEGRADED_REQUESTS", "2")
    get_settings.cache_clear()
    rate_limiter.reset()

    assert await rate_limiter.hit("k") is True
    assert await rate_limiter.hit("k") is True
    assert await rate_limiter.hit("k") is False  # tighter budget, not 100


async def test_degraded_memory_does_not_grow_without_bound(
    monkeypatch: pytest.MonkeyPatch, redis_down: None
) -> None:
    """Every distinct key is caller-chosen, so an unbounded dict is an OOM
    with extra steps."""
    monkeypatch.setenv("RATE_LIMIT_DEGRADED_REQUESTS", "1000")
    get_settings.cache_clear()
    rate_limiter.reset()

    for i in range(rate_limiter.MEMORY_MAX_KEYS + 500):
        await rate_limiter.hit(f"ratelimit:10.0.0.{i % 255}:/path/{i}")

    assert len(rate_limiter.tracked_keys()) <= rate_limiter.MEMORY_MAX_KEYS


async def test_expired_degraded_windows_are_reclaimed(
    monkeypatch: pytest.MonkeyPatch, redis_down: None
) -> None:
    """A key whose window has passed is dead weight; it must not be kept
    just because the cap has not been reached yet."""
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "0")  # every window instantly stale
    get_settings.cache_clear()
    rate_limiter.reset()

    for i in range(50):
        await rate_limiter.hit(f"stale:{i}")

    assert len(rate_limiter.tracked_keys()) < 50
