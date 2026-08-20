"""SecureRouter: every route is private and rate-limited unless explicitly public.

The threat model is a future session adding an endpoint and forgetting auth.
A route registered without public=True gets an auth dependency that resolves
the id.agri.in session cookie (D09) plus a rate limit; with no resolver
registered or no valid session it is a 401. public=True skips only the auth
dependency and records the route for the boot-time log.
"""

import inspect
import time
import uuid
from collections.abc import Awaitable, Callable
from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.types import DecoratedCallable
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from settings import get_settings
from shared.cache import get_redis
from shared.db import get_session
from shared.telemetry import get_logger

logger = get_logger(__name__)

PrincipalResolver = Callable[[Request, AsyncSession], Awaitable[object | None]]

_principal_resolver: PrincipalResolver | None = None


def register_principal_resolver(resolver: PrincipalResolver) -> None:
    """The identity module plugs real session auth in at app creation (D09).

    Indirection, not import: import-linter forbids shared -> modules, and the
    threat model (a route registered without public=True must never be open)
    holds either way - no resolver means every private route 401s.
    """
    global _principal_resolver
    _principal_resolver = resolver


def reset_principal_resolver() -> None:
    global _principal_resolver
    _principal_resolver = None


async def require_auth(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> None:
    """Session-cookie auth for every non-public route (D09). Unresolved and
    unregistered are the same 401 - fail closed, never open.

    Rides the request-scoped get_session dependency (FastAPI caches it, so
    the endpoint shares the same session/transaction - one connection per
    request, and test overrides of get_session apply here too)."""
    if _principal_resolver is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    principal = await _principal_resolver(request, session)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    request.state.principal = principal


async def optional_auth(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> None:
    """Attribute the caller when credentials are present; never 401.

    For guest-capable routes (declared public=True): a logged-in caller gets
    request.state.principal set exactly as require_auth would, an anonymous
    caller proceeds without one. Routes must treat the principal as optional."""
    if _principal_resolver is None:
        return
    principal = await _principal_resolver(request, session)
    if principal is not None:
        request.state.principal = principal


def require_role(request: Request, *allowed: str) -> uuid.UUID:
    """Fail-closed role gate for admin routers that cannot import
    modules.identity (import-linter independence). Returns the acting
    admin's user_id for audit. D21 extracts this from the four per-router
    _require_role copies; new code uses this one."""
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=403, detail="missing_role")
    roles = getattr(principal, "roles", ())
    if not any(role in roles for role in allowed):
        raise HTTPException(status_code=403, detail="missing_role")
    user_id = principal.user_id
    return user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))


class RateLimiter:
    """Fixed-window rate limiter: Redis-backed, with a degraded local window.

    When Redis answers, the count is shared by every worker and the budget is
    `rate_limit_requests`. When it does not, each process falls back to its own
    dict, and two things stop being true: the count is no longer shared, and
    the keys are no longer someone else's problem to expire.

    Both are handled here rather than by refusing service. A 503 on every route
    the moment Redis blinks trades a bounded abuse window for a total outage,
    which is the wrong way round for a public catalogue - the sensitive
    surfaces that genuinely should fail closed (OTP issuance, contact reveal)
    already do so in their own throttles.
    """

    # A per-process window handing out the full shared budget would multiply
    # the real limit by the worker count exactly when the shared counter is
    # gone, so degraded mode gets its own, smaller number.
    #
    # The dict is also bounded. Keys are `{ip}:{path}`, i.e. caller-chosen, so
    # an unbounded map during a long outage is a memory exhaustion primitive
    # that costs the attacker nothing but 404s.
    MEMORY_MAX_KEYS = 10_000
    _SWEEP_EVERY = 32

    def __init__(self) -> None:
        self._memory: dict[str, tuple[int, float]] = {}
        self._warned = False
        self._since_sweep = 0

    def reset(self) -> None:
        self._memory.clear()
        self._warned = False
        self._since_sweep = 0

    def tracked_keys(self) -> tuple[str, ...]:
        """Keys currently held by the degraded window (tests/introspection)."""
        return tuple(self._memory)

    async def hit(self, key: str) -> bool:
        settings = get_settings()
        window = settings.rate_limit_window_seconds
        try:
            count = await get_redis().incr(key)
            if int(count) == 1:
                await get_redis().expire(key, window)
            return int(count) <= settings.rate_limit_requests
        except (RedisError, OSError):
            # never MORE permissive than the configured shared budget: an
            # operator who tightens rate_limit_requests below the degraded
            # default would otherwise be loosened by a Redis outage
            degraded = min(settings.rate_limit_degraded_requests, settings.rate_limit_requests)
            if not self._warned:
                logger.warning(
                    "redis unreachable; rate limiting degraded to a per-process window "
                    "of %s per %ss",
                    degraded,
                    window,
                )
                self._warned = True
            return self._hit_memory(key, degraded, window)

    def _hit_memory(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        self._since_sweep += 1
        if self._since_sweep >= self._SWEEP_EVERY or len(self._memory) >= self.MEMORY_MAX_KEYS:
            self._sweep(now, window)
        count, started = self._memory.get(key, (0, now))
        if now - started >= window:
            count, started = 0, now
        count += 1
        self._memory[key] = (count, started)
        return count <= limit

    def _sweep(self, now: float, window: int) -> None:
        """Drop finished windows; if everything is still live, drop the oldest.

        Amortised over _SWEEP_EVERY calls, and only ever runs while Redis is
        down - the healthy path never touches this dict.
        """
        self._since_sweep = 0
        self._memory = {k: v for k, v in self._memory.items() if now - v[1] < window}
        if len(self._memory) >= self.MEMORY_MAX_KEYS:
            # all windows still open: keep the newest half, since the oldest
            # are the closest to expiring anyway
            newest = sorted(self._memory.items(), key=lambda kv: kv[1][1], reverse=True)
            self._memory = dict(newest[: self.MEMORY_MAX_KEYS // 2])


rate_limiter = RateLimiter()


@lru_cache(maxsize=8)
def _trusted_networks(spec: str) -> tuple[IPv4Network | IPv6Network, ...]:
    """Parse the comma-separated trusted_proxy_ips setting once per value.

    Unparseable entries are dropped with a warning rather than raising: a typo
    in this setting must not take the API down, and dropping it fails closed
    (that peer simply stops being trusted).
    """
    networks: list[IPv4Network | IPv6Network] = []
    for entry in spec.split(","):
        candidate = entry.strip()
        if not candidate:
            continue
        try:
            networks.append(ip_network(candidate, strict=False))
        except ValueError:
            logger.warning("ignoring unparseable trusted_proxy_ips entry: %r", candidate)
    return tuple(networks)


def _is_trusted_relay(peer: str, spec: str) -> bool:
    try:
        address = ip_address(peer)
    except ValueError:
        return False  # 'unknown', a unix socket, a hostname: not a declared relay
    return any(address in network for network in _trusted_networks(spec))


def client_ip(request: Request) -> str:
    """The caller's address: the socket peer, unless a declared relay vouched
    for someone else via X-Forwarded-For.

    A caller must never be able to nominate its own address here. This value
    keys the rate limiter (`ratelimit:{ip}:{path}`) and seeds the daily viewer
    pseudonym (directory/analytics.viewer_hash), so anyone who can choose it
    has neither a rate limit nor a stable pseudonym.

    X-Forwarded-For is not a forbidden header name, so page JavaScript can set
    it on a same-origin fetch, and the Next relays forward what they receive.
    An edge proxy does not fix that by itself either: Cloudflare APPENDS the
    real address to a client-supplied header rather than replacing it, so the
    leftmost entry stays attacker-chosen. Hence both conditions - the feature
    flag AND the peer being a relay the operator declared in trusted_proxy_ips.

    Undeclared peer, unset setting, or a forwarded value that is not an
    address: the socket peer wins. Behind a relay that means every visitor
    shares one bucket, which costs throughput and leaks nothing.
    """
    peer = request.client.host if request.client else "unknown"
    settings = get_settings()
    if not settings.trust_forwarded_for:
        return peer
    if not _is_trusted_relay(peer, settings.trusted_proxy_ips):
        return peer
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer
    # leftmost is the original client: each hop APPENDS, and every hop between
    # here and the visitor is trusted by construction once the peer is declared
    claimed = forwarded.split(",")[0].strip()
    try:
        ip_address(claimed)
    except ValueError:
        return peer  # the value crossed untrusted ground before the relay saw it
    return claimed


async def rate_limit(request: Request) -> None:
    key = f"ratelimit:{client_ip(request)}:{request.url.path}"
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
        if public:
            self.public_paths.append(f"{self.prefix}{path}")
        else:
            dependencies.insert(0, Depends(require_auth))
        # rate_limit goes in LAST so it ends up FIRST. FastAPI stops at the
        # first failing dependency, so with require_auth ahead of it an
        # unauthenticated request to a private route was never counted - while
        # still paying for a session lookup or an RS256 verification on every
        # attempt. Credential probing has to spend budget like anything else.
        dependencies.insert(0, Depends(rate_limit))
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
