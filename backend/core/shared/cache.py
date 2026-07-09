"""Redis client access (lazy singleton)."""

from redis.asyncio import Redis

from settings import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


def reset_redis() -> None:
    """Drop the singleton so the next call rebuilds from current settings (tests)."""
    global _redis
    _redis = None


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def check_cache() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False
