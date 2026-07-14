"""Monthly referral reset hook: observability only, never mutates."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import referrals
from scripts.coins_referral_reset import _main, monthly_reward_counts

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 7, 13, tzinfo=UTC)


async def _code_for(session: AsyncSession, referrer: uuid.UUID) -> str:
    return await referrals.get_or_create_code(session, referrer)


async def test_monthly_reward_counts_empty(db_session: AsyncSession) -> None:
    assert await monthly_reward_counts(db_session, NOW) == []


async def test_monthly_reward_counts_after_rewarded_referral(db_session: AsyncSession) -> None:
    referrer, referee = uuid.uuid4(), uuid.uuid4()
    code = await _code_for(db_session, referrer)
    await referrals.attribute(
        db_session, referee_id=referee, code=code, device_fingerprint=None, phone_prefix=None
    )
    await referrals.maybe_reward(db_session, referee_id=referee, now=NOW)

    counts = await monthly_reward_counts(db_session, NOW)

    assert counts == [(referrer, 1)]


async def test_monthly_reward_counts_excludes_prior_months(db_session: AsyncSession) -> None:
    referrer, referee = uuid.uuid4(), uuid.uuid4()
    code = await _code_for(db_session, referrer)
    await referrals.attribute(
        db_session, referee_id=referee, code=code, device_fingerprint=None, phone_prefix=None
    )
    await referrals.maybe_reward(db_session, referee_id=referee, now=NOW)

    next_month = datetime(2026, 8, 1, tzinfo=UTC)

    assert await monthly_reward_counts(db_session, next_month) == []


async def test_main_returns_0_with_no_referrals() -> None:
    assert await _main() == 0
