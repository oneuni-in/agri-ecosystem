"""DPDP rights: export, erasure lifecycle, reveal log (ID-U1 W4).

No HTTP here. Functions take the caller's session and flush; the router
commits, matching the rest of this module.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.dpdp_models import ErasureRequest
from modules.identity.models import Profile, User
from shared import dpdp
from shared.telemetry import get_logger

logger = get_logger(__name__)

# How long a person has to change their mind. Not mandated by the Act; chosen
# because the action is irreversible, the trigger is one tap, and a stolen
# session should not be able to destroy an account faster than its owner can
# notice and sign it out.
ERASURE_GRACE_DAYS = 7

OPEN_STATUSES = ("pending", "held")


class ErasureError(Exception):
    """.code is the API error detail."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ErasureView:
    status: str
    execute_after: datetime
    requested_at: datetime
    executed_at: datetime | None


async def open_request(session: AsyncSession, user_id: uuid.UUID) -> ErasureRequest | None:
    row = await session.scalar(
        select(ErasureRequest)
        .where(ErasureRequest.user_id == user_id, ErasureRequest.status.in_(OPEN_STATUSES))
        .order_by(ErasureRequest.created_at.desc())
        .limit(1)
    )
    return row if isinstance(row, ErasureRequest) else None


async def request_erasure(
    session: AsyncSession, user_id: uuid.UUID, *, now: datetime | None = None
) -> ErasureRequest:
    """Idempotent by design: asking twice returns the SAME request rather than
    stacking a second one or erroring. A person tapping delete again is
    expressing the same wish, and a duplicate would give the admin queue two
    rows for one decision."""
    moment = now or datetime.now(UTC)
    existing = await open_request(session, user_id)
    if existing is not None:
        return existing
    row = ErasureRequest(
        user_id=user_id,
        status="pending",
        execute_after=moment + timedelta(days=ERASURE_GRACE_DAYS),
    )
    session.add(row)
    await session.flush()
    return row


async def cancel_erasure(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    closed_by: uuid.UUID | None = None,
    now: datetime | None = None,
) -> ErasureRequest:
    """Withdrawing is always allowed while the request is open - including
    while it is HELD. A hold is a reason not to delete; it is never a reason
    to force someone to stay deleted."""
    row = await open_request(session, user_id)
    if row is None:
        raise ErasureError("no_open_request")
    row.status = "cancelled"
    row.closed_at = now or datetime.now(UTC)
    row.closed_by_user_id = closed_by
    await session.flush()
    return row


async def execute_due(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 50
) -> dict[str, Any]:
    """Run every erasure whose grace has elapsed. Called by the scheduled job
    and by the admin queue's "run now".

    Holds are re-checked HERE, at execution time, not at request time: a
    dispute opened during the grace window must still stop the deletion.
    """
    moment = now or datetime.now(UTC)
    due = (
        await session.scalars(
            select(ErasureRequest)
            .where(
                ErasureRequest.status.in_(OPEN_STATUSES),
                ErasureRequest.execute_after <= moment,
            )
            .order_by(ErasureRequest.created_at)
            .limit(limit)
        )
    ).all()
    executed: list[str] = []
    held: list[str] = []
    for row in due:
        holds = await dpdp.erasure_holds(session, row.user_id)
        if holds:
            row.status = "held"
            row.hold_reasons = ",".join(holds)
            held.append(str(row.id))
            continue
        await erase_user(session, row.user_id)
        row.status = "executed"
        row.hold_reasons = None
        row.executed_at = moment
        executed.append(str(row.id))
    await session.flush()
    return {"executed": executed, "held": held, "considered": len(due)}


async def erase_user(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    """Erase identity's own data, then every other module's through the seam.

    Identity is a SCRUB, not a row delete: users.id is referenced across the
    system (ledger entries, audit rows, this very request row), and cascading
    those away would destroy records that must survive - an immutable coins
    ledger cannot lose an entry because its subject left. So the row stays,
    stripped of everything that identifies a person, and status flips to
    'deleted' which every resolver already treats as gone (login denies,
    lookups return None, the handle stops resolving).
    """
    user = await session.get(User, user_id)
    if user is None:
        return {}
    # the handle must not linger as a public name, and must not collide with
    # a real one if someone later picks it
    user.agri_id = f"deleted-{uuid.uuid4().hex[:12]}"
    user.phone = f"deleted-{uuid.uuid4().hex}"
    user.phone_verified_at = None
    user.status = "deleted"
    profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is not None:
        profile.name = None
        profile.state = None
        profile.district = None
        profile.pincode = None
        profile.language = None
        profile.interests = []
        profile.avatar_key = None
        profile.completion_score = 0
    counts = await dpdp.run_erasers(session, user_id)
    await session.flush()
    logger.info(
        "dpdp.erased",
        extra={"extra_fields": {"sections": sorted(counts), "rows": sum(counts.values())}},
    )
    return counts


async def build_export(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    """The archive. Every module's section, plus a manifest naming which
    sections exist - so a reader can tell an EMPTY section from a MISSING
    one, which is the difference between "you have no coins" and "we did not
    give you your coins data"."""
    sections = await dpdp.collect_export(session, user_id)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "format": "agriid-dpdp-export/1",
        "sections_included": list(dpdp.registered_export_sections()),
        "data": sections,
    }
