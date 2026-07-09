# D01-B FastAPI Skeleton + SecureRouter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FastAPI modular-monolith skeleton where every route is private + rate-limited by default (401 until identity lands), proven by a pytest, with a one-command healthy Docker dev stack.

**Architecture:** `backend/core` is the Python project root; top-level import packages are `modules` (11 feature modules) and `shared` (infrastructure), plus root modules `main`/`settings`. `SecureRouter` (an `APIRouter` subclass) injects auth-stub + rate-limit dependencies on every route unless `public=True`, which records the route on a per-router public list aggregated into `app.state.public_routes` and logged on boot. import-linter enforces module independence.

**Tech Stack:** Python 3.13 (Docker truth; host 3.12 tooling), FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2 async + asyncpg, redis-py asyncio, httpx, pytest + pytest-asyncio, ruff, mypy --strict, import-linter, Docker multi-stage on python:3.13-slim, docker-compose.dev.yml (api, postgres:16, redis:7, meilisearch, minio).

## Global Constraints

- Branch `feat/d01b-fastapi-skeleton` off `dev`; PR targets `dev`. NEVER commit to main or dev directly.
- Conventional commits; final PR title `feat(d01b): fastapi skeleton + secure router`.
- NO real secrets anywhere. `.env.example` has every var name, NO real values. Dev-only credentials in compose (`app`/`app`, `minioadmin`) are documented as dev-only.
- No real JWT/auth logic (D08–09) · no DB tables/Alembic (D03) · no cross-module imports.
- Container runs non-root; base image `python:3.13-slim`; multi-stage build.
- mypy strict passes; `shared/` fully typed. Ruff clean. import-linter green and enforced in CI.
- Host Python is 3.12.10 and has no `uv` → use `python -m venv` + pip. `requires-python = ">=3.12"`; Docker pins 3.13.
- Frontend owns ports 3000–3004 (D01-A). API uses 8000; postgres 5432, redis 6379, meilisearch 7700, minio 9000/9001.
- Definition of done: compose stack healthy in one command; 401-default test green; boot log shows public routes == `['/health', '/health/deep']`; PR open to dev.
- Assumptions (confirm in PR description): modular monolith per ADR-A1 (no ADR docs exist in repo yet); MinIO stands in for R2 locally.

## File Structure

```
docker-compose.dev.yml                  # repo root — one command brings up the stack
.github/workflows/backend-ci.yml        # ruff, mypy, import-linter, pytest on PRs
backend/core/
  pyproject.toml                        # project + ruff/mypy/pytest/import-linter config
  .env.example                          # every env var name, no values
  Dockerfile                            # multi-stage, non-root
  .dockerignore
  main.py                               # app factory, health endpoints, boot log
  settings.py                           # pydantic-settings
  shared/
    __init__.py
    telemetry.py                        # logging setup
    cache.py                            # redis client singleton
    events.py                           # in-process async event bus
    security.py                         # SecureRouter + auth stub + rate limiter
    db.py                               # async engine/sessionmaker (no tables)
    storage.py                          # MinIO/R2 health check stub
  modules/
    __init__.py
    {identity,coins,directory,leads,content,market_data,ads,notify,search,billing,ai}/
      __init__.py
      router.py                         # SecureRouter instance, no routes yet
      service.py                        # docstring only
      models.py                         # docstring only
  tests/
    __init__.py
    conftest.py
    test_settings.py
    test_events.py
    test_secure_router.py               # THE 401-default test lives here
    test_main.py                        # public registry + health + boot log
```

---

### Task 1: Project scaffold, settings, telemetry

**Files:**
- Create: `backend/core/pyproject.toml`
- Create: `backend/core/settings.py`
- Create: `backend/core/.env.example`
- Create: `backend/core/shared/__init__.py`
- Create: `backend/core/shared/telemetry.py`
- Create: `backend/core/tests/__init__.py`
- Create: `backend/core/tests/conftest.py`
- Test: `backend/core/tests/test_settings.py`
- Modify: `.gitignore` (append Python section)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `settings.get_settings() -> Settings` (cached; fields listed below), `shared.telemetry.configure_logging(level: str) -> None`, `shared.telemetry.get_logger(name: str) -> logging.Logger`.

- [ ] **Step 1: Create venv and project config**

```powershell
cd d:\agri-ecosystem\backend\core   # create dirs first: backend/core/{shared,tests}
python -m venv .venv
```

Write `backend/core/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "agri-core"
version = "0.1.0"
description = "Agri ecosystem core API - FastAPI modular monolith"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29",
    "redis>=5.0",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "mypy>=1.10",
    "ruff>=0.5",
    "import-linter>=2.0",
]

[tool.setuptools]
py-modules = ["main", "settings"]

[tool.setuptools.packages.find]
include = ["modules*", "shared*"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "T20"]

[tool.ruff.lint.isort]
known-first-party = ["modules", "shared", "settings", "main"]

[tool.mypy]
python_version = "3.12"
strict = true
mypy_path = "."

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.importlinter]
root_packages = ["modules", "shared"]

[[tool.importlinter.contracts]]
name = "Modules must not import each other"
type = "independence"
modules = [
    "modules.identity",
    "modules.coins",
    "modules.directory",
    "modules.leads",
    "modules.content",
    "modules.market_data",
    "modules.ads",
    "modules.notify",
    "modules.search",
    "modules.billing",
    "modules.ai",
]

[[tool.importlinter.contracts]]
name = "Shared must not import modules"
type = "forbidden"
source_modules = ["shared"]
forbidden_modules = ["modules"]
```

Install: `.venv\Scripts\pip install -e .[dev]` (needs `shared/__init__.py`, `settings.py`, and a stub `main.py` to exist first — create `main.py` with just a docstring for now; Task 4 replaces it).

- [ ] **Step 2: Write the failing settings test**

`backend/core/tests/__init__.py` — empty. `backend/core/tests/conftest.py`:

```python
"""Shared test fixtures: reset cached global state between tests."""
from collections.abc import Iterator

import pytest

from settings import get_settings


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    yield
    get_settings.cache_clear()
```

`backend/core/tests/test_settings.py`:

```python
"""Settings load from environment with sane dev defaults."""
import pytest

from settings import get_settings


def test_defaults() -> None:
    settings = get_settings()
    assert settings.app_env == "dev"
    assert settings.rate_limit_requests == 60
    assert settings.rate_limit_window_seconds == 60
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "5")
    get_settings.cache_clear()
    assert get_settings().rate_limit_requests == 5


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests\test_settings.py -v`
Expected: FAIL / collection error — `settings` has no `get_settings`.

- [ ] **Step 4: Write settings.py and telemetry.py**

`backend/core/settings.py`:

```python
"""Application settings loaded from the environment via pydantic-settings."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # dev-only defaults; real values come from the environment
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/agri"
    redis_url: str = "redis://localhost:6379/0"
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_master_key: str = ""
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "agri-media"

    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`backend/core/shared/__init__.py` — empty. `backend/core/shared/telemetry.py`:

```python
"""Logging setup for the core service."""
import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
```

`backend/core/.env.example`:

```
# Copy to .env for local overrides. Never put real secrets in this file.
APP_ENV=dev
DEBUG=false
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000
DATABASE_URL=
REDIS_URL=
MEILISEARCH_URL=
MEILISEARCH_MASTER_KEY=
MINIO_ENDPOINT=
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
MINIO_BUCKET=
RATE_LIMIT_REQUESTS=60
RATE_LIMIT_WINDOW_SECONDS=60
```

Append to root `.gitignore`:

```
# python (backend)
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
backend/**/.env
```

- [ ] **Step 5: Run tests, ruff, mypy — all green**

Run: `.venv\Scripts\pytest tests\test_settings.py -v` → 3 PASS.
Run: `.venv\Scripts\ruff check .` and `.venv\Scripts\ruff format .` → clean.
Run: `.venv\Scripts\mypy .` → no errors.

- [ ] **Step 6: Commit**

```powershell
git add backend/core .gitignore docs/superpowers/plans/2026-07-09-d01b-fastapi-skeleton.md
git commit -m "feat(d01b): backend project scaffold with typed settings"
```

---

### Task 2: shared/cache.py and shared/events.py

**Files:**
- Create: `backend/core/shared/cache.py`
- Create: `backend/core/shared/events.py`
- Test: `backend/core/tests/test_events.py`
- Modify: `backend/core/tests/conftest.py` (reset redis singleton)

**Interfaces:**
- Consumes: `settings.get_settings()`.
- Produces: `shared.cache.get_redis() -> Redis`, `shared.cache.reset_redis() -> None`, `shared.cache.close_redis() -> None` (async), `shared.cache.check_cache() -> bool` (async); `shared.events.EventBus` with `subscribe(event: str, handler: Handler) -> None` and async `publish(event: str, payload: dict[str, Any]) -> None`; module-level `shared.events.bus`.

- [ ] **Step 1: Write failing event-bus tests**

`backend/core/tests/test_events.py`:

```python
"""In-process event bus delivers payloads to subscribers."""
from typing import Any

from shared.events import EventBus


async def test_publish_reaches_all_subscribers() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        received.append(payload)

    bus.subscribe("lead.created", handler)
    bus.subscribe("lead.created", handler)
    await bus.publish("lead.created", {"id": "abc"})
    assert received == [{"id": "abc"}, {"id": "abc"}]


async def test_publish_without_subscribers_is_a_noop() -> None:
    await EventBus().publish("nobody.listening", {})


async def test_events_are_isolated_by_name() -> None:
    bus = EventBus()
    received: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        received.append(payload)

    bus.subscribe("a", handler)
    await bus.publish("b", {"x": 1})
    assert received == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\pytest tests\test_events.py -v`
Expected: FAIL — `shared.events` does not exist.

- [ ] **Step 3: Implement events.py and cache.py**

`backend/core/shared/events.py`:

```python
"""Minimal in-process async event bus.

Modules communicate through this bus (or public service interfaces),
never by importing each other.
"""
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> None:
        self._handlers[event].append(handler)

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        for handler in self._handlers.get(event, []):
            await handler(payload)


bus = EventBus()
```

`backend/core/shared/cache.py`:

```python
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
```

Update `conftest.py` fixture body to also reset the redis singleton:

```python
"""Shared test fixtures: reset cached global state between tests."""
from collections.abc import Iterator

import pytest

from settings import get_settings
from shared.cache import reset_redis


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    yield
    get_settings.cache_clear()
    reset_redis()
```

- [ ] **Step 4: Run tests, ruff, mypy — green**

Run: `.venv\Scripts\pytest -v` → all PASS. `.venv\Scripts\ruff check .` clean. `.venv\Scripts\mypy .` clean.

- [ ] **Step 5: Commit**

```powershell
git add backend/core
git commit -m "feat(d01b): redis cache singleton and in-process event bus"
```

---

### Task 3: SecureRouter — private + rate-limited by default

**Files:**
- Create: `backend/core/shared/security.py`
- Test: `backend/core/tests/test_secure_router.py`
- Modify: `backend/core/tests/conftest.py` (reset rate limiter)

**Interfaces:**
- Consumes: `settings.get_settings()`, `shared.cache.get_redis()`, `shared.telemetry.get_logger()`.
- Produces: `shared.security.SecureRouter` (APIRouter subclass; verb decorators accept `public: bool = False`; instance attr `public_paths: list[str]`), `shared.security.require_auth(request: Request) -> None` (async, always raises 401), `shared.security.rate_limit(request: Request) -> None` (async, raises 429 over limit), `shared.security.rate_limiter: RateLimiter` with `reset() -> None`.

- [ ] **Step 1: Write THE failing tests**

`backend/core/tests/test_secure_router.py`:

```python
"""The Constitution's core guarantee: a thoughtlessly-added route is private
and rate-limited. THE test: no public=True -> 401."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from settings import get_settings
from shared.security import SecureRouter


class Message(BaseModel):
    detail: str


def make_client(router: SecureRouter) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_route_without_public_returns_401() -> None:
    router = SecureRouter()

    @router.get("/private")
    async def private_route() -> Message:  # pragma: no cover - never reached
        return Message(detail="secret")

    assert make_client(router).get("/private").status_code == 401


def test_all_verbs_are_private_by_default() -> None:
    router = SecureRouter()

    @router.post("/w")
    async def w() -> Message:  # pragma: no cover
        return Message(detail="w")

    @router.put("/x")
    async def x() -> Message:  # pragma: no cover
        return Message(detail="x")

    @router.patch("/y")
    async def y() -> Message:  # pragma: no cover
        return Message(detail="y")

    @router.delete("/z")
    async def z() -> Message:  # pragma: no cover
        return Message(detail="z")

    client = make_client(router)
    assert client.post("/w").status_code == 401
    assert client.put("/x").status_code == 401
    assert client.patch("/y").status_code == 401
    assert client.delete("/z").status_code == 401


def test_public_route_bypasses_auth() -> None:
    router = SecureRouter()

    @router.get("/open", public=True)
    async def open_route() -> Message:
        return Message(detail="hello")

    response = make_client(router).get("/open")
    assert response.status_code == 200
    assert response.json() == {"detail": "hello"}


def test_public_route_recorded_with_router_prefix() -> None:
    router = SecureRouter(prefix="/demo")

    @router.get("/open", public=True)
    async def open_route() -> Message:  # pragma: no cover
        return Message(detail="hello")

    assert router.public_paths == ["/demo/open"]


def test_private_route_not_in_public_paths() -> None:
    router = SecureRouter()

    @router.get("/private")
    async def private_route() -> Message:  # pragma: no cover
        return Message(detail="secret")

    assert router.public_paths == []


def test_route_without_response_model_is_rejected() -> None:
    router = SecureRouter()
    with pytest.raises(RuntimeError, match="response_model"):

        @router.get("/untyped")
        async def untyped_route():  # type: ignore[no-untyped-def]
            return {"detail": "nope"}


def test_rate_limit_kicks_in_via_memory_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # unreachable -> fallback
    get_settings.cache_clear()

    router = SecureRouter()

    @router.get("/limited", public=True)
    async def limited_route() -> Message:
        return Message(detail="ok")

    client = make_client(router)
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 429
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\pytest tests\test_secure_router.py -v`
Expected: FAIL — `shared.security` does not exist.

- [ ] **Step 3: Implement shared/security.py**

```python
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
```

Note: if mypy reports an override incompatibility on `add_api_route` or the verb
methods (base signatures carry dozens of keyword params absorbed here by
`**kwargs: Any`), append `# type: ignore[override]` to the offending `def` line —
that is the only permitted ignore in this file.

Update `conftest.py` `_reset_state` to also call `rate_limiter.reset()`:

```python
"""Shared test fixtures: reset cached global state between tests."""
from collections.abc import Iterator

import pytest

from settings import get_settings
from shared.cache import reset_redis
from shared.security import rate_limiter


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    yield
    get_settings.cache_clear()
    reset_redis()
    rate_limiter.reset()
```

- [ ] **Step 4: Run tests, ruff, mypy — green**

Run: `.venv\Scripts\pytest -v` → all PASS (401-default test green).
Run: `.venv\Scripts\ruff check .` and `.venv\Scripts\mypy .` → clean.

- [ ] **Step 5: Commit**

```powershell
git add backend/core
git commit -m "feat(d01b): SecureRouter - private and rate-limited by default"
```

---

### Task 4: Modules, db/storage, health endpoints, app factory

**Files:**
- Create: `backend/core/shared/db.py`
- Create: `backend/core/shared/storage.py`
- Create: `backend/core/modules/__init__.py`
- Create: for each of `identity coins directory leads content market_data ads notify search billing ai`: `backend/core/modules/<name>/{__init__.py,router.py,service.py,models.py}`
- Rewrite: `backend/core/main.py`
- Test: `backend/core/tests/test_main.py`

**Interfaces:**
- Consumes: `SecureRouter`, `get_settings`, `check_cache`, `close_redis`, `configure_logging`, `get_logger`.
- Produces: `shared.db.get_engine() -> AsyncEngine`, `shared.db.get_sessionmaker() -> async_sessionmaker[AsyncSession]`, `shared.db.check_database() -> bool` (async); `shared.storage.check_storage() -> bool` (async); `main.create_app() -> FastAPI` with `app.state.public_routes: list[str]`; module-level `main.app`; each `modules.<name>.router.router: SecureRouter` with prefix `/<name>` (underscores kept: `/market_data`).

- [ ] **Step 1: Write failing tests**

`backend/core/tests/test_main.py`:

```python
"""App factory wiring: health endpoints public, everything else absent/private,
public-route registry logged on boot."""
import logging

import pytest
from fastapi.testclient import TestClient

from main import create_app


def test_health_is_public() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_deep_reports_per_service_status() -> None:
    # no backing services running in unit tests -> degraded 503 with all-False map
    response = TestClient(create_app()).get("/health/deep")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert set(body["services"]) == {"postgres", "redis", "meilisearch", "minio"}
    assert all(up is False for up in body["services"].values())


def test_public_routes_are_exactly_the_health_endpoints() -> None:
    app = create_app()
    assert app.state.public_routes == ["/health", "/health/deep"]


def test_boot_log_lists_public_routes(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        with TestClient(create_app()):
            pass
    assert "public routes: ['/health', '/health/deep']" in caplog.text
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\pytest tests\test_main.py -v`
Expected: FAIL — `main` has no `create_app` (stub from Task 1).

- [ ] **Step 3: Implement db.py, storage.py, module scaffolds**

`backend/core/shared/db.py`:

```python
"""Async SQLAlchemy engine and session factory. Tables and Alembic land in D03."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from settings import get_settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def check_database() -> bool:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
```

`backend/core/shared/storage.py`:

```python
"""Object storage access (MinIO locally, standing in for R2). Client lands later."""
import httpx

from settings import get_settings


async def check_storage() -> bool:
    url = f"{get_settings().minio_endpoint}/minio/health/live"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        return response.status_code == 200
    except httpx.HTTPError:
        return False
```

For EACH module name in `identity coins directory leads content market_data ads notify search billing ai` (scripted loop is fine), create:

`modules/<name>/__init__.py` — empty.

`modules/<name>/router.py` (identity shown; substitute the module name in prefix/tags):

```python
"""Identity module routes. Endpoints land in later specs."""
from shared.security import SecureRouter

router = SecureRouter(prefix="/identity", tags=["identity"])
```

`modules/<name>/service.py`:

```python
"""Identity module public service interface. Implementation lands in later specs."""
```

`modules/<name>/models.py`:

```python
"""Identity module ORM models. Tables land in D03."""
```

`modules/__init__.py` — empty.

- [ ] **Step 4: Implement main.py**

```python
"""FastAPI application factory for the agri core service."""
import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response
from pydantic import BaseModel

from modules.ads.router import router as ads_router
from modules.ai.router import router as ai_router
from modules.billing.router import router as billing_router
from modules.coins.router import router as coins_router
from modules.content.router import router as content_router
from modules.directory.router import router as directory_router
from modules.identity.router import router as identity_router
from modules.leads.router import router as leads_router
from modules.market_data.router import router as market_data_router
from modules.notify.router import router as notify_router
from modules.search.router import router as search_router
from settings import get_settings
from shared.cache import check_cache, close_redis
from shared.db import check_database
from shared.security import SecureRouter
from shared.storage import check_storage
from shared.telemetry import configure_logging, get_logger

logger = get_logger(__name__)

MODULE_ROUTERS = [
    ads_router,
    ai_router,
    billing_router,
    coins_router,
    content_router,
    directory_router,
    identity_router,
    leads_router,
    market_data_router,
    notify_router,
    search_router,
]


class HealthResponse(BaseModel):
    status: str


class DeepHealthResponse(BaseModel):
    status: str
    services: dict[str, bool]


health_router = SecureRouter(tags=["health"])


@health_router.get("/health", public=True)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


async def _check_meilisearch() -> bool:
    url = f"{get_settings().meilisearch_url}/health"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


async def _bounded(check: Awaitable[bool]) -> bool:
    try:
        return await asyncio.wait_for(check, timeout=2.0)
    except Exception:
        return False


@health_router.get("/health/deep", public=True)
async def health_deep(response: Response) -> DeepHealthResponse:
    names = ["postgres", "redis", "meilisearch", "minio"]
    results = await asyncio.gather(
        _bounded(check_database()),
        _bounded(check_cache()),
        _bounded(_check_meilisearch()),
        _bounded(check_storage()),
    )
    services = dict(zip(names, results, strict=True))
    healthy = all(services.values())
    if not healthy:
        response.status_code = 503
    return DeepHealthResponse(status="ok" if healthy else "degraded", services=services)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("public routes: %s", app.state.public_routes)
    yield
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(title="agri core", lifespan=lifespan)
    public_routes: list[str] = []
    for router in [health_router, *MODULE_ROUTERS]:
        app.include_router(router)
        public_routes.extend(router.public_paths)
    app.state.public_routes = public_routes
    return app


app = create_app()
```

- [ ] **Step 5: Run tests, ruff, mypy — green**

Run: `.venv\Scripts\pytest -v` → all PASS (test_health_deep takes a few seconds: connection refusals + 2s bounds).
Run: `.venv\Scripts\ruff check .` and `.venv\Scripts\mypy .` → clean.

- [ ] **Step 6: Commit**

```powershell
git add backend/core
git commit -m "feat(d01b): app factory, module scaffolds, public health endpoints"
```

---

### Task 5: import-linter enforcement + backend CI

**Files:**
- Create: `.github/workflows/backend-ci.yml`
- (import-linter contracts already in `pyproject.toml` from Task 1)

**Interfaces:**
- Consumes: everything prior; the `[tool.importlinter]` contracts from Task 1.
- Produces: CI gate — ruff, mypy, lint-imports, pytest must pass on PRs touching `backend/**`.

- [ ] **Step 1: Run import-linter and verify it passes**

Run: `cd backend/core; .venv\Scripts\lint-imports`
Expected: both contracts KEPT.

- [ ] **Step 2: Prove it fails on violation**

Temporarily add `from modules.coins.service import *  # noqa` to `modules/identity/service.py`, rerun `lint-imports`.
Expected: contract "Modules must not import each other" BROKEN, exit code 1. **Revert the edit** and rerun to confirm green.

- [ ] **Step 3: Write the CI workflow**

`.github/workflows/backend-ci.yml`:

```yaml
name: backend-ci

on:
  pull_request:
    paths:
      - "backend/**"
      - ".github/workflows/backend-ci.yml"
  push:
    branches: [dev, main]
    paths:
      - "backend/**"

jobs:
  checks:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend/core
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -e .[dev]
      - run: ruff format --check .
      - run: ruff check .
      - run: mypy .
      - run: lint-imports
      - run: pytest -q
```

- [ ] **Step 4: Commit**

```powershell
git add .github/workflows/backend-ci.yml
git commit -m "ci(d01b): backend checks - ruff, mypy, import-linter, pytest"
```

---

### Task 6: Dockerfile + docker-compose.dev.yml

**Files:**
- Create: `backend/core/Dockerfile`
- Create: `backend/core/.dockerignore`
- Create: `docker-compose.dev.yml` (repo root)

**Interfaces:**
- Consumes: the installable project from Task 1 (`pip install .` works because `py-modules`/`packages.find` are configured).
- Produces: `docker compose -f docker-compose.dev.yml up -d --wait` → 5 healthy services; API on :8000.

- [ ] **Step 1: Write Dockerfile and .dockerignore**

`backend/core/.dockerignore`:

```
.venv
__pycache__
*.pyc
.pytest_cache
.mypy_cache
.ruff_cache
.env
```

`backend/core/Dockerfile`:

```dockerfile
# Backend truth lives here: Python 3.13. Host Python is tooling only.
FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN python -m venv /venv
WORKDIR /src
COPY . .
RUN /venv/bin/pip install .

FROM python:3.13-slim

RUN useradd --create-home --uid 1000 appuser
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"
USER appuser
WORKDIR /home/appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write docker-compose.dev.yml (repo root)**

```yaml
name: agri-dev

services:
  api:
    build: ./backend/core
    ports:
      - "8000:8000"
    environment:
      APP_ENV: dev
      DATABASE_URL: postgresql+asyncpg://app:app@postgres:5432/agri
      REDIS_URL: redis://redis:6379/0
      MEILISEARCH_URL: http://meilisearch:7700
      MINIO_ENDPOINT: http://minio:9000
    volumes:
      - ./backend/core:/app
    working_dir: /app
    command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      meilisearch:
        condition: service_healthy
      minio:
        condition: service_healthy
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status == 200 else 1)"
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 15s

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app # dev-only credentials
      POSTGRES_DB: agri
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d agri"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  meilisearch:
    image: getmeili/meilisearch:v1.13
    environment:
      MEILI_ENV: development
    ports:
      - "7700:7700"
    volumes:
      - meilidata:/meili_data
    healthcheck:
      test: ["CMD-SHELL", "wget --no-verbose --spider http://localhost:7700/health || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 10

  minio:
    image: minio/minio:latest
    command: ["server", "/data", "--console-address", ":9001"]
    environment:
      MINIO_ROOT_USER: minioadmin # dev-only credentials
      MINIO_ROOT_PASSWORD: minioadmin # dev-only credentials
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - miniodata:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  pgdata:
  redisdata:
  meilidata:
  miniodata:
```

- [ ] **Step 3: Bring the stack up and verify healthy**

Run: `docker compose -f docker-compose.dev.yml up -d --build --wait` (from repo root; allow several minutes for first pull/build).
Expected: exits 0 with all 5 services healthy. If a healthcheck binary is missing in an image (`wget`/`mc`), swap per image docs (`curl -fs`, or `curl -f http://localhost:9000/minio/health/live`) — verify with `docker compose ps` until all healthy.

Run: `docker compose -f docker-compose.dev.yml ps` → 5x `healthy`.
Run: `curl.exe -s http://localhost:8000/health/deep` → HTTP 200, all four services `true`.
Run: `docker compose -f docker-compose.dev.yml logs api | Select-String "public routes"` → shows `['/health', '/health/deep']`.

- [ ] **Step 4: Tear down and commit**

```powershell
docker compose -f docker-compose.dev.yml down
git add backend/core/Dockerfile backend/core/.dockerignore docker-compose.dev.yml
git commit -m "feat(d01b): docker dev stack - api, postgres, redis, meilisearch, minio"
```

---

### Task 7: Final verification + PR

**Files:** none new.

- [ ] **Step 1: Full local gate**

From `backend/core`, run in order; all must pass:

```powershell
.venv\Scripts\ruff format --check .
.venv\Scripts\ruff check .
.venv\Scripts\mypy .
.venv\Scripts\lint-imports
.venv\Scripts\pytest -v
```

- [ ] **Step 2: Push and open PR to dev**

```powershell
git push -u origin feat/d01b-fastapi-skeleton
gh pr create --base dev --title "feat(d01b): fastapi skeleton + secure router" --body "<summary: SecureRouter 401-by-default + rate limit, public registry boot log, health endpoints, docker stack, import-linter + CI. Assumptions confirmed in body: modular monolith per ADR-A1; MinIO stands in for R2 locally.>"
```

PR body must list the Definition of Done evidence: 401-default test output, `docker compose ps` healthy output, boot-log line, lint-imports output.
