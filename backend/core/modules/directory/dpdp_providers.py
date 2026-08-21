"""Directory's DPDP sections (ID-U1 W4).

Registered into shared.dpdp by main.create_app(). Identity orchestrates the
three rights but may not read these tables; this is directory answering for
its own data, in its own module.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.leads_models import ContactReveal, Inquiry
from modules.directory.models import Business, Report
from shared.dpdp import RevealRecord


async def reveal_log(session: AsyncSession, user_id: uuid.UUID) -> list[RevealRecord]:
    """Every time this person's contact details were shown to a business.

    `contact_reveals` is append-only by grant and carries no contact VALUE by
    design (D18) - it records that a reveal happened, not what was revealed.
    Joined to the business so the answer names a shop rather than a UUID.
    """
    rows = (
        await session.execute(
            select(ContactReveal.created_at, Business.name)
            .join(Business, Business.id == ContactReveal.business_id, isouter=True)
            .where(ContactReveal.user_id == user_id)
            .order_by(ContactReveal.created_at.desc())
            .limit(500)
        )
    ).all()
    return [
        RevealRecord(revealed_at=at, business_name=name, source="directory") for at, name in rows
    ]


async def directory_export(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    inquiries = (
        await session.execute(
            select(Inquiry.type, Inquiry.status, Inquiry.pincode, Inquiry.created_at)
            .where(Inquiry.from_user_id == user_id)
            .order_by(Inquiry.created_at.desc())
            .limit(500)
        )
    ).all()
    owned = (
        await session.scalars(
            select(Business.name).where(Business.owner_user_id == user_id).limit(100)
        )
    ).all()
    reveals = await reveal_log(session, user_id)
    return {
        "inquiries": [
            {
                "type": t,
                "status": s,
                "pincode": p,
                "created_at": created.isoformat(),
            }
            for t, s, p, created in inquiries
        ],
        "businesses_owned": list(owned),
        "contact_reveals": [
            {"revealed_at": r.revealed_at.isoformat(), "business": r.business_name} for r in reveals
        ],
    }


async def erasure_hold(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    """Reasons directory needs this deletion to wait for a human.

    Both are genuine unresolved obligations rather than bureaucracy:

    - an OPEN report this person filed is a dispute still being decided, and
      erasing the reporter mid-decision destroys one side of it;
    - a business they still OWN would be orphaned - a live public listing
      whose owner no longer exists cannot be claimed, corrected or taken
      down by anyone.

    Returned as a short code; the admin queue shows it, the user never does.
    """
    open_reports = await session.scalar(
        select(func.count())
        .select_from(Report)
        .where(Report.reporter_user_id == user_id, Report.moderation_status == "pending")
    )
    if open_reports:
        return "open_report"
    owned = await session.scalar(
        select(func.count()).select_from(Business).where(Business.owner_user_id == user_id)
    )
    if owned:
        return "owns_business"
    return None


async def erase(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Detach this person from directory's rows rather than deleting them.

    An inquiry a vendor answered is the VENDOR's record too, and a reveal log
    entry is the evidence that a consent-gated disclosure happened. Deleting
    either would erase someone else's history and destroy an audit trail that
    exists to protect the very person being erased. Both are anonymised: the
    user link goes, the event stays.
    """
    touched = 0
    inquiries = (
        await session.scalars(select(Inquiry).where(Inquiry.from_user_id == user_id))
    ).all()
    for inquiry in inquiries:
        inquiry.from_user_id = None  # exactly the shape a guest submission has
        touched += 1
    reveals = (
        await session.scalars(select(ContactReveal).where(ContactReveal.user_id == user_id))
    ).all()
    for reveal in reveals:
        await session.delete(reveal)
        touched += 1
    await session.flush()
    return touched
