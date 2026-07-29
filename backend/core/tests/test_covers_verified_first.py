"""Verified-first covers() ordering (M1 NN#2): verification_status leads the
sort and the keyset, ahead of the D26 premium tier. Only 'verified' ranks up
- 'pending' sorts with 'unverified', so sitting in the D16 queue buys nothing
(fake-verification threat)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.covers import covers, decode_covers_cursor, encode_covers_cursor
from modules.directory.models import Business
from shared.pagination import InvalidCursorError

pytestmark = pytest.mark.asyncio


async def _covered_business(
    session: AsyncSession,
    name: str,
    *,
    branch_at: tuple[float, float] = (10.9232, 76.9686),
    tier: str = "free",
    verification: str = "unverified",
) -> Business:
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
    )
    await service.set_coverage(
        session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    lat, lng = branch_at
    await service.add_branch(
        session,
        owner_user_id=owner,
        business_id=business.id,
        address="1 Main Rd",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode="641001",
        lat=Decimal(str(lat)),
        lng=Decimal(str(lng)),
    )
    if tier != "free":
        business.subscription_tier = tier  # simulates the admin tier route
    if verification != "unverified":
        business.verification_status = verification  # simulates the D16 decision
    await session.flush()
    return business


async def test_verified_outranks_unverified_at_equal_relevance(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """NN#2: same tier, same distance - verification is the only difference."""
    await _covered_business(db_session, "Unverified")
    await _covered_business(db_session, "Verified", verification="verified")
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Verified", "Unverified"]


async def test_verified_free_outranks_unverified_premium(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """The owner-approved order: trust leads, the paid tier follows."""
    await _covered_business(db_session, "PremiumUnverified", tier="premium")
    await _covered_business(db_session, "FreeVerified", verification="verified")
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["FreeVerified", "PremiumUnverified"]


async def test_pending_does_not_rank_up(db_session: AsyncSession, tn_geo_sample: None) -> None:
    """The D16 queue is the ONLY path to the boost - being in it is not."""
    await _covered_business(db_session, "Pending", verification="pending")
    await _covered_business(db_session, "Verified", verification="verified")
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Verified", "Pending"]


async def test_tier_then_distance_still_order_within_a_verification_band(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _covered_business(db_session, "VerFreeNear", verification="verified")
    await _covered_business(
        db_session,
        "VerPremFar",
        tier="premium",
        verification="verified",
        branch_at=(11.2832, 76.9686),
    )
    await _covered_business(db_session, "UnverPremNear", tier="premium")
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["VerPremFar", "VerFreeNear", "UnverPremNear"]


async def test_keyset_pages_across_the_verified_boundary(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """The half that fails silently: no gaps, no dupes, across the boundary."""
    for i in range(3):
        await _covered_business(db_session, f"Ver{i}", verification="verified")
    for i in range(3):
        await _covered_business(db_session, f"Unver{i}")
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        page = await covers(db_session, pincode="641001", cursor=cursor, limit=2)
        seen.extend(i.name for i in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(seen) == 6
    assert len(set(seen)) == 6
    assert all(n.startswith("Ver") for n in seen[:3])


async def test_cursor_round_trip_is_four_fields() -> None:
    ident = uuid.uuid4()
    encoded = encode_covers_cursor(0, 1, 4200, ident)
    assert decode_covers_cursor(encoded) == (0, 1, 4200, ident)


async def test_pre_m1_three_field_cursor_is_rejected() -> None:
    """D26 cursors in flight fail closed with a 400, not a wrong page."""
    import base64

    legacy = base64.urlsafe_b64encode(b"1:4200:" + uuid.uuid4().hex.encode()).decode().rstrip("=")
    with pytest.raises(InvalidCursorError):
        decode_covers_cursor(legacy)
