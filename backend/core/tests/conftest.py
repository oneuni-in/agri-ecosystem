"""Shared test fixtures: reset cached global state between tests, and provide
a migrated throwaway Postgres database + a flushed Redis DB for integration
tests. DB/redis fixtures skip (visibly) when the backing service is down;
CI always runs them via its service containers.
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from modules.identity.oauth_keys import reset_oauth_keys
from modules.identity.otp_drivers import MockDriver
from modules.identity.rbac import reset_permission_cache
from modules.notify.drivers import MockEmailDriver, MockNotifySmsDriver
from settings import get_settings
from shared.cache import reset_redis
from shared.db import Base, reset_engine
from shared.flags import reset_flag_cache
from shared.metrics import reset_metrics
from shared.security import rate_limiter, reset_principal_resolver
from shared.storage import reset_storage

# D12: the notify lifespan worker is gated on `notify_worker_enabled and
# app_env != "test"`, but APP_ENV is never set to "test" here or in CI's
# pytest job (ci.yml pytest step; see test_settings.py which pins the "dev"
# default) - only the explicit-otp_test_peek code path cares about "test" as
# a value. Without this, `with TestClient(create_app())` in test_main.py/
# test_metrics.py would boot a real background worker (real DB/redis, not
# the per-test fixtures) on every run. setdefault() so a test that wants the
# worker can still monkeypatch+cache_clear around it.
os.environ.setdefault("NOTIFY_WORKER_ENABLED", "false")

TEST_DB_NAME = "agri_test"
TEST_REDIS_DB = 9


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    yield
    get_settings.cache_clear()
    reset_redis()
    reset_storage()
    reset_engine()
    reset_flag_cache()
    rate_limiter.reset()
    reset_metrics()
    MockDriver.reset()
    reset_oauth_keys()
    reset_principal_resolver()
    reset_permission_cache()
    MockEmailDriver.reset()
    MockNotifySmsDriver.reset()


@pytest.fixture(scope="session")
def database_url() -> str:
    """Recreate and migrate the test database once per session; return its
    runtime (app_rt) URL. DROP/CREATE and the alembic migration run with the
    admin (table-owner) role; db_session and everything downstream connect
    as app_rt, matching the app's runtime DB identity (D12)."""
    admin_url = make_url(get_settings().database_admin_url)
    admin_test_url = admin_url.set(database=TEST_DB_NAME).render_as_string(hide_password=False)
    runtime_test_url = (
        make_url(get_settings().database_url)
        .set(database=TEST_DB_NAME)
        .render_as_string(hide_password=False)
    )

    async def _prepare() -> None:
        engine = create_async_engine(
            admin_url.render_as_string(hide_password=False),
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
        )
        async with engine.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
            await conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
        await engine.dispose()

    try:
        asyncio.run(asyncio.wait_for(_prepare(), timeout=15))
    except Exception as exc:
        pytest.skip(f"postgres unreachable at {admin_url.host}:{admin_url.port} - {exc!r}")

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=os.environ | {"ALEMBIC_DATABASE_URL": admin_test_url},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed on {TEST_DB_NAME}:\n{result.stderr}")
    return runtime_test_url


@pytest.fixture(scope="session")
def admin_database_url(database_url: str) -> str:
    """Owner-credentials URL on the same migrated test DB (tamper tests only)."""
    return (
        make_url(get_settings().database_admin_url)
        .set(database=TEST_DB_NAME)
        .render_as_string(hide_password=False)
    )


@pytest.fixture(scope="session")
def _scratch_tables_ready(admin_database_url: str) -> None:
    """Several suites (test_mixins/test_slugs/test_pagination/test_ownership/
    test_i18n) declare throwaway `test_*` model classes and create their
    tables at runtime via `Base.metadata.create_all(checkfirst=True)`. Those
    tables aren't part of any migration. Since app_rt (D12) has DML only, no
    CREATE, provision them once per session with admin credentials; each
    test's own create_all call then finds them already present and no-ops."""

    async def _create() -> None:
        engine = create_async_engine(admin_database_url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())


@pytest.fixture
async def db_session(database_url: str, _scratch_tables_ready: None) -> AsyncIterator[AsyncSession]:
    """Session inside an outer transaction that always rolls back."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        outer = await conn.begin()
        maker = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with maker() as session:
            yield session
        await outer.rollback()
    await engine.dispose()


@pytest.fixture
async def otp_redis(redis_client: Redis, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Redis]:
    """Point shared.cache.get_redis at the flushed test redis DB (OTP suites)."""
    url = get_settings().redis_url.rsplit("/", 1)[0] + f"/{TEST_REDIS_DB}"
    monkeypatch.setenv("REDIS_URL", url)
    get_settings.cache_clear()
    reset_redis()
    yield redis_client


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """Client on a dedicated redis DB, flushed before each test."""
    url = get_settings().redis_url.rsplit("/", 1)[0] + f"/{TEST_REDIS_DB}"
    client: Redis = Redis.from_url(url, decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        pytest.skip(f"redis unreachable - {exc!r}")
    await client.flushdb()
    yield client
    await client.aclose()
