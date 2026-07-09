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

from settings import get_settings
from shared.cache import reset_redis
from shared.db import reset_engine
from shared.flags import reset_flag_cache
from shared.security import rate_limiter

TEST_DB_NAME = "agri_test"
TEST_REDIS_DB = 9


@pytest.fixture(autouse=True)
def _reset_state() -> Iterator[None]:
    yield
    get_settings.cache_clear()
    reset_redis()
    reset_engine()
    reset_flag_cache()
    rate_limiter.reset()


@pytest.fixture(scope="session")
def database_url() -> str:
    """Recreate and migrate the test database once per session; return its URL."""
    admin_url = make_url(get_settings().database_url)
    test_url = admin_url.set(database=TEST_DB_NAME).render_as_string(hide_password=False)

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
        env=os.environ | {"ALEMBIC_DATABASE_URL": test_url},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed on {TEST_DB_NAME}:\n{result.stderr}")
    return test_url


@pytest.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
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
