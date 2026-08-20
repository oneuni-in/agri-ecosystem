# backend/core/tests/test_reference_table_grants.py
"""Reference tables the application only ever reads.

0013 handed app_rt DML on every table in eleven schemas. 0051 took the RBAC
catalog back; this is the next slice - five tables whose rows arrive from a
migration and are only ever SELECTed at runtime.

The slice is deliberately small. A mechanical sweep is not safe here: the
first pass of this audit was written as a script that looked for `Model(`,
and it reported ads.impressions as unwritten. It is written, by
`model = Impression if kind == "imp" else Click; session.add(model(...))` in
modules/ads/router.py - an indirect construction the pattern cannot see. A
revoke based on that output would have taken the ads beacon down in
production, so every table below was read by hand instead, across modules/,
shared/ and scripts/ (which matter because scripts connect as app_rt, not as
the owner).

Deliberately NOT included:
  - identity.emails: read-only today, but it is user data with a verified_at
    column, so an email-verification flow would write it. Not worth the test
    churn for a table that is one feature away from needing the grant back.
  - directory.categories, market.commodities, identity.oauth_clients,
    coins.rules, content.sources: each has 13-24 mentions in prod code that
    have not been read line by line yet. Unread is not the same as read-only.
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

READ_ONLY = (
    ("identity", "addresses"),
    ("market", "crop_calendars"),
    ("market", "msp"),
    ("market", "schemes"),
    ("notify", "templates"),
)


@pytest.fixture
async def runtime_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.mark.parametrize(("schema", "table"), READ_ONLY)
async def test_reference_table_is_select_only(
    runtime_engine: AsyncEngine, schema: str, table: str
) -> None:
    async with runtime_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = 'app_rt' AND table_schema = :schema AND table_name = :table"
            ),
            {"schema": schema, "table": table},
        )
    assert {row[0] for row in rows} == {"SELECT"}


async def test_the_ads_beacon_keeps_its_writes(runtime_engine: AsyncEngine) -> None:
    """The table the mechanical pass got wrong, pinned so a future sweep that
    repeats the mistake fails here instead of in production."""
    async with runtime_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT has_table_privilege('app_rt', 'ads.impressions', 'INSERT'), "
                "has_table_privilege('app_rt', 'ads.clicks', 'INSERT')"
            )
        )
    assert rows.one() == (True, True)
