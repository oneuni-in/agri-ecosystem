"""SecureRouter: every route is private and rate-limited unless explicitly public.

The threat model is a future session adding an endpoint and forgetting auth.
A route registered without public=True gets an auth dependency that returns
401 unconditionally (real auth lands in D08-09) plus a rate limit. public=True
skips only the auth dependency and records the route for the boot-time log.
"""

import inspect
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.types import DecoratedCallable
from redis.exceptions import RedisError

from settings import get_settings
from shared.cache import get_redis
from shared.telemetry import get_logger

logger = get_logger(__name__)


async def require_auth(request: Request) -> None:
    """Auth stub: unconditionally 401 until the identity module lands (D08-09)."""
    raise HTTPException(status_code=401, detail="Authentication required")


class RateLimiter:
    """Fixed-window rate limiter: Redis-backed, in-memory fallback for dev."""

    def __init__(self) -> None:
        self._memory: dict[str, tuple[int, float]] = {}
        self._warned = False

    def reset(self) -> None:
        self._memory.clear()
        self._warned = False

    async def hit(self, key: str) -> bool:
        settings = get_settings()
        limit = settings.rate_limit_requests
        window = settings.rate_limit_window_seconds
        try:
            count = await get_redis().incr(key)
            if int(count) == 1:
                await get_redis().expire(key, window)
            return int(count) <= limit
        except (RedisError, OSError):
            if not self._warned:
                logger.warning("redis unreachable; falling back to in-memory rate limiting")
                self._warned = True
        return self._hit_memory(key, limit, window)

    def _hit_memory(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        count, started = self._memory.get(key, (0, now))
        if now - started >= window:
            count, started = 0, now
        count += 1
        self._memory[key] = (count, started)
        return count <= limit


rate_limiter = RateLimiter()


async def rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    key = f"ratelimit:{client}:{request.url.path}"
    if not await rate_limiter.hit(key):
        raise HTTPException(status_code=429, detail="Too many requests")


def _has_return_annotation(endpoint: Callable[..., Any]) -> bool:
    return inspect.signature(endpoint).return_annotation is not inspect.Signature.empty


class SecureRouter(APIRouter):
    """APIRouter where every route is private + rate-limited unless public=True."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.public_paths: list[str] = []

    def add_api_route(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        public: bool = False,
        **kwargs: Any,
    ) -> None:
        if kwargs.get("response_model") is None and not _has_return_annotation(endpoint):
            raise RuntimeError(
                f"route {self.prefix}{path} must declare a response_model "
                "or a return type annotation"
            )
        dependencies = list(kwargs.pop("dependencies", None) or [])
        dependencies.insert(0, Depends(rate_limit))
        if public:
            self.public_paths.append(f"{self.prefix}{path}")
        else:
            dependencies.insert(0, Depends(require_auth))
        kwargs["dependencies"] = dependencies
        super().add_api_route(path, endpoint, **kwargs)

    def _secure_route(
        self, path: str, methods: list[str], *, public: bool, **kwargs: Any
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        def decorator(func: DecoratedCallable) -> DecoratedCallable:
            self.add_api_route(path, func, methods=methods, public=public, **kwargs)
            return func

        return decorator

    def get(
        self, path: str, *, public: bool = False, **kwargs: Any
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        return self._secure_route(path, ["GET"], public=public, **kwargs)

    def post(
        self, path: str, *, public: bool = False, **kwargs: Any
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        return self._secure_route(path, ["POST"], public=public, **kwargs)

    def put(
        self, path: str, *, public: bool = False, **kwargs: Any
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        return self._secure_route(path, ["PUT"], public=public, **kwargs)

    def patch(
        self, path: str, *, public: bool = False, **kwargs: Any
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        return self._secure_route(path, ["PATCH"], public=public, **kwargs)

    def delete(
        self, path: str, *, public: bool = False, **kwargs: Any
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        return self._secure_route(path, ["DELETE"], public=public, **kwargs)
