"""Referral codes + attribution + delayed reward (D13.D).

Anti-farm posture: the reward is DELAYED to the referee's profile_100 event
(never at signup), and the referrer is capped at REFERRER_MONTHLY_CAP paid
referrals per calendar month. The referee's own reward is a strict once-ever
(total_cap=1 in the rules table + a user-scoped idempotency key), so a
referee can never be credited more than once no matter how many times
maybe_reward is invoked.
"""

import secrets
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import service
from modules.coins.models import Referral, ReferralCode

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars


def _mint() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


async def get_or_create_code(session: AsyncSession, user_id: uuid.UUID) -> str:
    existing = await session.scalar(
        select(ReferralCode.code).where(ReferralCode.user_id == user_id)
    )
    if existing is not None:
        return existing
    for _ in range(5):
        code = _mint()
        try:
            async with session.begin_nested():
                session.add(ReferralCode(user_id=user_id, code=code))
                await session.flush()
            return code
        except IntegrityError:
            # unique(code) or unique(user_id) collision; re-read on the latter
            hit = await session.scalar(
                select(ReferralCode.code).where(ReferralCode.user_id == user_id)
            )
            if hit is not None:
                return hit
    raise RuntimeError("could not mint a unique referral code")


REFERRER_MONTHLY_CAP = 20


class ReferralCapError(Exception):
    """Referrer exceeded the monthly referral reward cap."""


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def attribute(
    session: AsyncSession,
    *,
    referee_id: uuid.UUID,
    code: str,
    device_fingerprint: str | None,
    phone_prefix: str | None,
) -> Referral | None:
    """Resolve `code` to a referrer and link `referee_id` to them as `pending`.

    Returns None on an unknown code or a self-referral. `referee_id` is
    unique on `Referral`, so a referee who is already attributed (to anyone)
    gets back their existing row unchanged - first attribution wins.
    """
    referrer_id = await session.scalar(
        select(ReferralCode.user_id).where(ReferralCode.code == code)
    )
    if referrer_id is None or referrer_id == referee_id:
        return None  # unknown code or self-referral
    existing = await session.scalar(select(Referral).where(Referral.referee_id == referee_id))
    if existing is not None:
        return existing  # unique(referee_id): first attribution wins
    referral = Referral(
        referrer_id=referrer_id,
        referee_id=referee_id,
        code=code,
        device_fingerprint=device_fingerprint,
        phone_prefix=phone_prefix,
        status="pending",
    )
    try:
        async with session.begin_nested():
            session.add(referral)
            await session.flush()
    except IntegrityError:
        winner: Referral | None = await session.scalar(
            select(Referral).where(Referral.referee_id == referee_id)
        )
        return winner
    return referral


async def maybe_reward(session: AsyncSession, *, referee_id: uuid.UUID, now: datetime) -> None:
    """Pay the delayed referral reward on the referee's profile_100 event.

    The referee always gets their one-time 100 (the reward is delayed to
    here, never paid at signup). The referrer gets 250 unless they have
    already been paid for REFERRER_MONTHLY_CAP referrals this calendar
    month; when capped, the referrer award is skipped but the referral is
    still marked `rewarded` so it is not retried. Idempotent: the award
    idempotency keys plus the pending-status guard mean a second call is a
    no-op.
    """
    referral = await session.scalar(
        select(Referral).where(Referral.referee_id == referee_id, Referral.status == "pending")
    )
    if referral is None:
        return
    # Referee reward is strictly once-per-referee-ever: total_cap=1 in the
    # rules table backs this, and the idempotency key is user-scoped (not
    # referral-scoped) so it can never be paid twice under any replay.
    await service.award(
        session,
        user_id=referee_id,
        rule_code="referral_referee",
        ref_id=str(referral.id),
        idempotency_key=f"referral_referee:{referee_id}",
        now=now,
    )
    # Referrer earns 250 per referral, unless already at the 20/month cap.
    rewarded_this_month = await session.scalar(
        select(func.count())
        .select_from(Referral)
        .where(
            Referral.referrer_id == referral.referrer_id,
            Referral.rewarded_at >= month_start(now),
        )
    )
    if (rewarded_this_month or 0) < REFERRER_MONTHLY_CAP:
        await service.award(
            session,
            user_id=referral.referrer_id,
            rule_code="referral_referrer",
            ref_id=str(referral.id),
            idempotency_key=f"referral_referrer:{referral.id}",
            now=now,
        )
    referral.status = "rewarded"
    referral.rewarded_at = now
    await session.flush()
