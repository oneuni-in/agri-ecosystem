"""Coins' DPDP sections (ID-U1 W4).

Registered into shared.dpdp by main.create_app(). Coins exports; it does NOT
register an eraser, and that is the interesting decision here.

The ledger is immutable by database trigger (D13): entries cannot be updated
or deleted, and the balance is their sum. Erasing a person's entries would
either fail against the trigger or, if forced, silently change the platform's
accounting for everyone. The entries carry no personal data of their own -
only a user_id, a reason code and an amount - and once identity scrubs the
user row that id points at nobody. So coins answers the ACCESS right in full
and leaves the erasure right to the row that actually identifies a person.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import service
from modules.coins.models import LedgerEntry, Referral, ReferralCode


async def coins_export(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    entries = (
        await session.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.user_id == user_id)
            .order_by(LedgerEntry.created_at.desc())
            .limit(1000)
        )
    ).all()
    code = await session.scalar(select(ReferralCode.code).where(ReferralCode.user_id == user_id))
    referred = await session.scalar(select(Referral.status).where(Referral.referee_id == user_id))
    return {
        "balance": await service.balance(session, user_id),
        "referral_code": code,
        "was_referred": referred is not None,
        "entries": [
            {
                "delta": e.delta,
                "reason": e.reason_code,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
    }
