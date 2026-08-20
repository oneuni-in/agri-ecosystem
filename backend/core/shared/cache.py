"""Redis client access (lazy singleton, per event loop)."""

import asyncio

from redis.asyncio import Redis

from settings import get_settings

_redis: Redis | None = None
_loop: asyncio.AbstractEventLoop | None = None


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None  # called from sync code; nothing to bind to yet


def get_redis() -> Redis:
    """The shared client, rebuilt if the event loop it was made on is gone.

    A redis-py connection belongs to the loop that opened it: reuse it from a
    different loop and the write future is None, which surfaces as a bare
    AttributeError deep inside the connection rather than anything about
    loops. Under uvicorn there is one loop for the process lifetime, so this
    check never fires. It fires for anything calling asyncio.run() more than
    once - the cron and worker scripts - and for TestClient, which runs each
    request on its own loop.
    """
    global _redis, _loop
    running = _running_loop()
    if _redis is None or (running is not None and running is not _loop):
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
        _loop = running
    return _redis


def reset_redis() -> None:
    """Drop the singleton so the next call rebuilds from current settings (tests)."""
    global _redis, _loop
    _redis = None
    _loop = None


async def close_redis() -> None:
    global _redis, _loop
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        _loop = None


async def check_cache() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False
