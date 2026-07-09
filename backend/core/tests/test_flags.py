"""Feature flags: DB-backed, read through a short in-process cache,
fail-closed for unknown keys, seeded with the launch kill-switches."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.flags import FeatureFlag, flag_enabled, reset_flag_cache


async def test_unknown_flag_is_disabled(db_session: AsyncSession) -> None:
    assert await flag_enabled("does_not_exist", session=db_session) is False


async def test_enabled_flag_reads_true(db_session: AsyncSession) -> None:
    db_session.add(FeatureFlag(key="new_thing", enabled=True, description="test flag"))
    await db_session.flush()

    assert await flag_enabled("new_thing", session=db_session) is True


async def test_reads_are_cached_until_reset(db_session: AsyncSession) -> None:
    flag = FeatureFlag(key="cached_thing", enabled=True, description="test flag")
    db_session.add(flag)
    await db_session.flush()

    assert await flag_enabled("cached_thing", session=db_session) is True

    flag.enabled = False
    await db_session.flush()
    # stale-but-fast: the cache still answers True
    assert await flag_enabled("cached_thing", session=db_session) is True

    reset_flag_cache()
    assert await flag_enabled("cached_thing", session=db_session) is False


async def test_migration_seeds_launch_kill_switches(db_session: AsyncSession) -> None:
    seeded = (
        await db_session.scalars(
            select(FeatureFlag).where(FeatureFlag.key.in_(["billing_enabled", "ads_enabled"]))
        )
    ).all()
    assert {flag.key: flag.enabled for flag in seeded} == {
        "billing_enabled": False,
        "ads_enabled": False,
    }
