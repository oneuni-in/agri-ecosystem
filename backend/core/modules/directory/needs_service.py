"""Needs service (D25): fan-out routing to ALL covering vendors, per-user
daily cap, ownership, child bookkeeping.

Fan-out deliberately inverts D18's one-inquiry-one-inbox rule: needs are
authed-only (phone-verified poster), so the guest-spam amplification that
justified single-routing does not apply; the cap pair (need_post_daily_cap x
need_fanout_limit) bounds inbox flooding instead."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.covers import covers
from modules.directory.leads_models import Inquiry, Need
from modules.directory.leads_service import NoCoverageError
from modules.directory.models import Business
from settings import get_settings
from shared.cache import get_redis

_DAY_SECONDS = 86400


class NeedsError(Exception):
    pass


class NeedNotFoundError(NeedsError):
    pass


class NeedCapExceededError(NeedsError):
    pass


class NeedsUnavailableError(NeedsError):
    pass


@dataclass(frozen=True, slots=True)
class RoutedVendor:
    id: uuid.UUID
    name: str
    owner_user_id: uuid.UUID | None


def _fanout_limit() -> int:
    return get_settings().need_fanout_limit


async def claim_need_slot(user_id: uuid.UUID, *, now: datetime) -> None:
    """Fail-closed daily post cap (reveal.py precedent): Redis down means 503,
    never an uncapped post; increment-before-act costs a slot on crash."""
    cap = get_settings().need_post_daily_cap
    key = f"need:{user_id}:{now.strftime('%Y%m%d')}"
    try:
        redis = get_redis()
        count = int(await redis.incr(key))
        if count == 1:
            await redis.expire(key, _DAY_SECONDS)
    except RedisError as exc:
        raise NeedsUnavailableError() from exc
    if count > cap:
        raise NeedCapExceededError()


async def route_need(session: AsyncSession, *, pincode: str) -> list[RoutedVendor]:
    """All covering vendors for the pincode, nearest-first, capped by
    need_fanout_limit. Raises NoCoverageError when covers() yields nothing
    (ungeocoded pincode or genuinely no coverage - same contract as D18)."""
    page = await covers(session, pincode=pincode, limit=_fanout_limit())
    if not page.items:
        raise NoCoverageError(pincode)
    ids = [item.id for item in page.items]
    owner_rows = await session.execute(
        select(Business.id, Business.owner_user_id).where(Business.id.in_(ids))
    )
    owners = {row.id: row.owner_user_id for row in owner_rows}
    return [
        RoutedVendor(id=item.id, name=item.name, owner_user_id=owners.get(item.id))
        for item in page.items
    ]


async def get_owned_need(session: AsyncSession, user_id: uuid.UUID, need_id: uuid.UUID) -> Need:
    """IDOR contract: someone else's need and a missing one are the SAME 404."""
    need = await session.scalar(
        select(Need).where(Need.id == need_id, Need.from_user_id == user_id)
    )
    if need is None:
        raise NeedNotFoundError(str(need_id))
    return need


async def close_open_children(session: AsyncSession, need_id: uuid.UUID) -> None:
    """Vendor-side bookkeeping when the user fulfils/closes a need: every
    still-open child inquiry closes so inboxes reflect it."""
    await session.execute(
        update(Inquiry)
        .where(Inquiry.need_id == need_id, Inquiry.status != "closed")
        .values(status="closed")
    )
