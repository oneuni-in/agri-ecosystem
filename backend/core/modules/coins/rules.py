"""Coins rules engine (D13) - EVERY award routes through here; there is no
cap bypass. AgriCoins are NOT money.

Sprint-1 caps (once / 1-per-day) are enforced by deterministic idempotency
keys + the UNIQUE(idempotency_key) constraint, which is race-free. Numeric
caps (daily/weekly/total > 1) are enforced by check_numeric_caps for any
future rule that needs them; the referral 20/month cap lives in referrals.py.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins.models import LedgerEntry, Rule

_ONCE_PER_USER = {"signup_complete", "profile_100", "referral_referee"}


class RuleNotActiveError(Exception):
    """Rule is unknown, disabled, or outside its valid window."""


class CapExceededError(Exception):
    """Awarding would exceed a numeric per-user cap."""


def deterministic_key(
    rule_code: str, user_id: uuid.UUID, *, day: str | None = None, ref_id: str | None = None
) -> str:
    if rule_code == "daily_visit":
        assert day is not None, "daily_visit requires a day (yyyy-mm-dd)"
        return f"daily_visit:{user_id}:{day}"
    if rule_code in _ONCE_PER_USER and ref_id is None:
        return f"{rule_code}:{user_id}"
    assert ref_id is not None, f"{rule_code} requires an explicit ref_id for its idem key"
    return f"{rule_code}:{ref_id}"


async def load_active_rule(session: AsyncSession, code: str, now: datetime) -> Rule:
    rule = await session.get(Rule, code)
    if rule is None or not rule.active:
        raise RuleNotActiveError(f"rule {code} is not active")
    if rule.valid_from is not None and now < rule.valid_from:
        raise RuleNotActiveError(f"rule {code} not yet valid")
    if rule.valid_to is not None and now >= rule.valid_to:
        raise RuleNotActiveError(f"rule {code} expired")
    return rule


async def check_numeric_caps(
    session: AsyncSession, rule: Rule, user_id: uuid.UUID, now: datetime
) -> None:
    windows = [
        (rule.daily_cap, now - timedelta(days=1)),
        (rule.weekly_cap, now - timedelta(days=7)),
        (rule.total_cap, None),
    ]
    for cap, since in windows:
        if cap is None or cap <= 1:
            continue  # <=1 caps are enforced by the deterministic unique key
        stmt = (
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.user_id == user_id, LedgerEntry.reason_code == rule.code)
        )
        if since is not None:
            stmt = stmt.where(LedgerEntry.created_at >= since)
        count = await session.scalar(stmt)
        if (count or 0) >= cap:
            raise CapExceededError(f"rule {rule.code} cap {cap} reached")
