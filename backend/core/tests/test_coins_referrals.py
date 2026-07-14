"""Referral attribution at signup, reward on referee profile_100, 20/month cap."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import referrals, service

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 7, 13, tzinfo=UTC)


async def _code_for(session: AsyncSession, referrer: uuid.UUID) -> str:
    return await referrals.get_or_create_code(session, referrer)


async def test_attribute_links_referee_to_referrer(db_session: AsyncSession) -> None:
    referrer, referee = uuid.uuid4(), uuid.uuid4()
    code = await _code_for(db_session, referrer)
    ref = await referrals.attribute(
        db_session,
        referee_id=referee,
        code=code,
        device_fingerprint="fp",
        phone_prefix="9198",
    )
    assert ref is not None
    assert ref.referrer_id == referrer
    assert ref.status == "pending"


async def test_self_referral_ignored(db_session: AsyncSession) -> None:
    u = uuid.uuid4()
    code = await _code_for(db_session, u)
    assert (
        await referrals.attribute(
            db_session, referee_id=u, code=code, device_fingerprint=None, phone_prefix=None
        )
        is None
    )


async def test_reward_pays_both_on_profile_100(db_session: AsyncSession) -> None:
    referrer, referee = uuid.uuid4(), uuid.uuid4()
    code = await _code_for(db_session, referrer)
    await referrals.attribute(
        db_session, referee_id=referee, code=code, device_fingerprint=None, phone_prefix=None
    )
    await referrals.maybe_reward(db_session, referee_id=referee, now=NOW)
    assert await service.balance(db_session, referrer) == 250
    assert await service.balance(db_session, referee) == 100


async def test_reward_is_idempotent(db_session: AsyncSession) -> None:
    referrer, referee = uuid.uuid4(), uuid.uuid4()
    code = await _code_for(db_session, referrer)
    await referrals.attribute(
        db_session, referee_id=referee, code=code, device_fingerprint=None, phone_prefix=None
    )
    await referrals.maybe_reward(db_session, referee_id=referee, now=NOW)
    await referrals.maybe_reward(db_session, referee_id=referee, now=NOW)
    assert await service.balance(db_session, referrer) == 250
    assert await service.balance(db_session, referee) == 100


async def test_monthly_cap_stops_referrer_award(db_session: AsyncSession) -> None:
    referrer = uuid.uuid4()
    code = await _code_for(db_session, referrer)
    # 20 rewarded referrals this month
    for _i in range(20):
        referee = uuid.uuid4()
        await referrals.attribute(
            db_session, referee_id=referee, code=code, device_fingerprint=None, phone_prefix=None
        )
        await referrals.maybe_reward(db_session, referee_id=referee, now=NOW)
    assert await service.balance(db_session, referrer) == 250 * 20
    # 21st referee: referee still gets 100, referrer does NOT exceed cap
    referee21 = uuid.uuid4()
    await referrals.attribute(
        db_session, referee_id=referee21, code=code, device_fingerprint=None, phone_prefix=None
    )
    await referrals.maybe_reward(db_session, referee_id=referee21, now=NOW)
    assert await service.balance(db_session, referrer) == 250 * 20  # unchanged
    assert await service.balance(db_session, referee21) == 100
