"""Premium-first covers() ordering (D26 NN#2): tier_rank leads the sort and
the keyset, so a premium business beats a nearer free one and pagination
across the tier boundary is gap- and dupe-free."""

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
    branch_at: tuple[float, float],
    tier: str = "free",
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
    if tier == "premium":
        business.subscription_tier = "premium"  # simulates the admin route
        await session.flush()
    return business


async def test_premium_outranks_nearer_free(db_session: AsyncSession, tn_geo_sample: None) -> None:
    await _covered_business(db_session, "NearFree", branch_at=(10.9232, 76.9686))  # ~0 km
    await _covered_business(
        db_session, "FarPremium", branch_at=(11.2832, 76.9686), tier="premium"
    )  # ~40 km
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["FarPremium", "NearFree"]
    assert page.items[0].subscription_tier == "premium"


async def test_distance_orders_within_a_tier(db_session: AsyncSession, tn_geo_sample: None) -> None:
    await _covered_business(db_session, "PremFar", branch_at=(11.2832, 76.9686), tier="premium")
    await _covered_business(db_session, "PremNear", branch_at=(10.9232, 76.9686), tier="premium")
    await _covered_business(db_session, "FreeNear", branch_at=(10.9232, 76.9686))
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["PremNear", "PremFar", "FreeNear"]


async def test_keyset_pages_across_tier_boundary(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    for index, name in enumerate(["P1", "P2", "P3"]):
        await _covered_business(
            db_session, name, branch_at=(10.9232 + index * 0.02, 76.9686), tier="premium"
        )
    for index, name in enumerate(["F1", "F2", "F3"]):
        await _covered_business(db_session, name, branch_at=(10.9232 + index * 0.02, 76.9686))
    seen: list[str] = []
    cursor: str | None = None
    while True:
        page = await covers(db_session, pincode="641001", cursor=cursor, limit=2)
        seen.extend(i.name for i in page.items)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert seen == ["P1", "P2", "P3", "F1", "F2", "F3"]  # no gaps, no dupes


async def test_coverage_edit_updates_covers(db_session: AsyncSession, tn_geo_sample: None) -> None:
    """NN#4: the coverage editor's whole-list PUT semantics must be visible
    in covers() immediately - add shows the business, remove hides it."""
    business = await _covered_business(db_session, "Editable", branch_at=(10.9232, 76.9686))
    owner = business.owner_user_id
    assert owner is not None
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Editable"]
    # remove 641001 (full-replace with a different pincode)
    await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id, pincodes=["641002"]
    )
    page = await covers(db_session, pincode="641001")
    assert page.items == []
    # re-add it
    await service.set_coverage(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        pincodes=["641001", "641002"],
    )
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Editable"]


async def test_old_two_field_cursor_is_invalid(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    import base64

    stale = base64.urlsafe_b64encode(f"12345:{uuid.uuid4().hex}".encode()).decode().rstrip("=")
    with pytest.raises(InvalidCursorError):
        await covers(db_session, pincode="641001", cursor=stale)


def test_cursor_roundtrip() -> None:
    last_id = uuid.uuid4()
    assert decode_covers_cursor(encode_covers_cursor(0, 987, last_id)) == (0, 987, last_id)
