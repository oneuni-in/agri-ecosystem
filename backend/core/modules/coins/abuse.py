"""Referral abuse clustering (D13.D). Groups referrals by shared device
fingerprint / phone prefix under one referrer; large clusters become
abuse_flags for admin review. Voids are compensating entries only (admin
action, not here) - this module only detects/flags, never awards or voids."""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins.models import AbuseFlag, Referral


async def scan_clusters(session: AsyncSession, *, min_cluster: int = 3) -> list[AbuseFlag]:
    """Scan pending/rewarded referrals for shared-device or shared-phone-prefix
    clusters under one referrer. Any group with >= min_cluster members creates
    an open AbuseFlag for each member referral not already flagged open.
    Idempotent across repeated calls."""
    referrals_rows = (
        await session.scalars(select(Referral).where(Referral.status.in_(("pending", "rewarded"))))
    ).all()
    already: set[uuid.UUID] = set(
        (
            await session.scalars(select(AbuseFlag.referral_id).where(AbuseFlag.status == "open"))
        ).all()
    )

    groups: dict[tuple[str, uuid.UUID, str], list[Referral]] = defaultdict(list)
    for r in referrals_rows:
        if r.device_fingerprint:
            groups[("device", r.referrer_id, r.device_fingerprint)].append(r)
        if r.phone_prefix:
            groups[("phone_prefix", r.referrer_id, r.phone_prefix)].append(r)

    created: list[AbuseFlag] = []
    for (reason, referrer_id, value), members in groups.items():
        if len(members) < min_cluster:
            continue
        for r in members:
            if r.id in already:
                continue
            flag = AbuseFlag(
                referral_id=r.id,
                cluster_reason=reason,
                details={"referrer_id": str(referrer_id), "value": value, "size": len(members)},
            )
            session.add(flag)
            already.add(r.id)
            created.append(flag)
    await session.flush()
    return created
