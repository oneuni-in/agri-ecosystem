"""Rules engine: active/window gating, deterministic keys, numeric caps."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import rules, service
from modules.coins.models import Rule

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


async def test_deterministic_keys() -> None:
    uid = uuid.uuid4()
    assert rules.deterministic_key("signup_complete", uid) == f"signup_complete:{uid}"
    assert (
        rules.deterministic_key("daily_visit", uid, day="2026-07-13")
        == f"daily_visit:{uid}:2026-07-13"
    )


async def test_once_rule_key_ignores_ref_id() -> None:
    uid = uuid.uuid4()
    for rule_code in ("signup_complete", "profile_100", "referral_referee"):
        assert rules.deterministic_key(rule_code, uid, ref_id="anything") == f"{rule_code}:{uid}"


async def test_non_once_rule_requires_ref_id() -> None:
    uid = uuid.uuid4()
    with pytest.raises(ValueError):
        rules.deterministic_key("referral_referrer", uid)
    assert rules.deterministic_key("referral_referrer", uid, ref_id="r1") == "referral_referrer:r1"


async def test_award_once_rule_credits_once(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    key = rules.deterministic_key("signup_complete", uid)
    e1 = await service.award(
        db_session,
        user_id=uid,
        rule_code="signup_complete",
        ref_id="signup_complete",
        idempotency_key=key,
        now=NOW,
    )
    e2 = await service.award(
        db_session,
        user_id=uid,
        rule_code="signup_complete",
        ref_id="signup_complete",
        idempotency_key=key,
        now=NOW,
    )
    assert e1.id == e2.id
    assert await service.balance(db_session, uid) == 100


async def test_daily_visit_second_same_day_is_idempotent(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    key = rules.deterministic_key("daily_visit", uid, day="2026-07-13")
    await service.award(
        db_session,
        user_id=uid,
        rule_code="daily_visit",
        ref_id="2026-07-13",
        idempotency_key=key,
        now=NOW,
    )
    await service.award(
        db_session,
        user_id=uid,
        rule_code="daily_visit",
        ref_id="2026-07-13",
        idempotency_key=key,
        now=NOW,
    )
    assert await service.balance(db_session, uid) == 5


async def test_inactive_rule_raises(db_session: AsyncSession) -> None:
    r = await db_session.get(Rule, "signup_complete")
    assert r is not None
    r.active = False
    await db_session.flush()
    with pytest.raises(rules.RuleNotActiveError):
        await service.award(
            db_session,
            user_id=uuid.uuid4(),
            rule_code="signup_complete",
            ref_id="x",
            idempotency_key="k",
            now=NOW,
        )


async def test_window_gating_before_valid_from(db_session: AsyncSession) -> None:
    r = await db_session.get(Rule, "profile_100")
    assert r is not None
    r.valid_from = NOW + timedelta(days=1)
    await db_session.flush()
    with pytest.raises(rules.RuleNotActiveError):
        await service.award(
            db_session,
            user_id=uuid.uuid4(),
            rule_code="profile_100",
            ref_id="x",
            idempotency_key="k2",
            now=NOW,
        )


async def test_window_gating_after_valid_to(db_session: AsyncSession) -> None:
    r = await db_session.get(Rule, "profile_100")
    assert r is not None
    r.valid_to = NOW - timedelta(days=1)
    await db_session.flush()
    with pytest.raises(rules.RuleNotActiveError):
        await service.award(
            db_session,
            user_id=uuid.uuid4(),
            rule_code="profile_100",
            ref_id="x",
            idempotency_key="k3",
            now=NOW,
        )


async def test_numeric_daily_cap_blocks_third(db_session: AsyncSession) -> None:
    # simulate a future rule with daily_cap=2 by editing daily_visit's cap
    uid = uuid.uuid4()
    r = await db_session.get(Rule, "daily_visit")
    assert r is not None
    r.daily_cap = 2
    await db_session.flush()
    for i in range(2):
        await service.award(
            db_session,
            user_id=uid,
            rule_code="daily_visit",
            ref_id=f"r{i}",
            idempotency_key=f"dv:{uid}:{i}",
            now=NOW,
        )
    with pytest.raises(rules.CapExceededError):
        await service.award(
            db_session,
            user_id=uid,
            rule_code="daily_visit",
            ref_id="r2",
            idempotency_key=f"dv:{uid}:2",
            now=NOW,
        )
