# backend/core/tests/test_slug_redirect_limit.py
"""A 404 must not be a free database query.

SecureRouter attaches the limiter as a route dependency, so it only ever runs
for paths that MATCHED a route. A path that matches nothing skips it entirely
- and SlugRedirectMiddleware then runs `find_redirect` against Postgres for
every unmatched GET/HEAD, to see whether the path is an old slug that moved.

That is one query per request, on a path the caller invents, with nothing
counting. Cheap to send, not cheap to serve.

The lookup stays (real visitors follow stale links, and 301s are why the slug
history exists), but it now spends the same budget as everything else. Over
budget, the 404 is returned as-is: the redirect is a courtesy, and dropping it
under flood is the right thing to drop.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from settings import get_settings
from shared import security
from shared.middleware import SlugRedirectMiddleware
from shared.security import rate_limiter


class _DeadRedis:
    async def incr(self, key: str) -> int:
        raise RedisError("unreachable")

    async def expire(self, key: str, window: int) -> bool:  # pragma: no cover
        raise RedisError("unreachable")


@pytest.fixture
def redis_down(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(security, "get_redis", lambda: _DeadRedis())
    rate_limiter.reset()
    yield


def make_client(lookups: list[str], target: str | None = None) -> TestClient:
    async def lookup(path: str) -> str | None:
        lookups.append(path)
        return target

    app = FastAPI()
    app.add_middleware(SlugRedirectMiddleware, lookup=lookup)
    return TestClient(app)


def test_a_flood_of_404s_stops_costing_lookups(
    monkeypatch: pytest.MonkeyPatch, redis_down: None
) -> None:
    monkeypatch.setenv("RATE_LIMIT_DEGRADED_REQUESTS", "3")
    get_settings.cache_clear()

    lookups: list[str] = []
    client = make_client(lookups)
    for i in range(12):
        assert client.get(f"/no-such-page-{i}").status_code == 404

    assert len(lookups) == 3  # the rest were refused before touching the DB


def test_a_real_moved_slug_still_redirects(
    monkeypatch: pytest.MonkeyPatch, redis_down: None
) -> None:
    """The limit must not cost an ordinary visitor their 301."""
    monkeypatch.setenv("RATE_LIMIT_DEGRADED_REQUESTS", "10")
    get_settings.cache_clear()

    lookups: list[str] = []
    client = make_client(lookups, target="/directory/businesses/new-slug")
    response = client.get("/directory/businesses/old-slug", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "/directory/businesses/new-slug"


def test_non_404_responses_never_reach_the_limiter(
    monkeypatch: pytest.MonkeyPatch, redis_down: None
) -> None:
    """Only unmatched GET/HEAD pay. A 200 must not spend the 404 budget, or a
    busy page could exhaust it for the visitors who genuinely followed an old
    link."""
    monkeypatch.setenv("RATE_LIMIT_DEGRADED_REQUESTS", "1")
    get_settings.cache_clear()

    lookups: list[str] = []

    async def lookup(path: str) -> str | None:  # pragma: no cover - never called
        lookups.append(path)
        return None

    app = FastAPI()
    app.add_middleware(SlugRedirectMiddleware, lookup=lookup)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"detail": "ok"}

    client = TestClient(app)
    for _ in range(5):
        assert client.get("/ok").status_code == 200
    assert lookups == []

    # the 404 budget is untouched, so a genuine miss still gets its lookup
    assert client.get("/missing").status_code == 404
    assert lookups == ["/missing"]
