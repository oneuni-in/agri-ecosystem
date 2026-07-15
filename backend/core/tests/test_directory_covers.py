"""covers(pincode): distance ordering from the searched pincode's centroid to
the nearest geocoded branch (primary-pincode fallback, unlocatable sentinel),
compound (distance_m, id) keyset paging. Non-negotiable #1: covers(641001)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.covers import (
    UNLOCATABLE_M,
    covers,
    decode_covers_cursor,
    encode_covers_cursor,
)
from shared.db import soft_delete
from shared.pagination import InvalidCursorError

pytestmark = pytest.mark.asyncio


async def _covered_business(
    session: AsyncSession,
    name: str,
    *,
    branch_at: tuple[float, float] | None = None,
    primary: str = "641001",
    pincode: str = "641001",
):
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode=primary
    )
    await service.set_coverage(
        session, owner_user_id=owner, business_id=business.id, pincodes=[pincode]
    )
    if branch_at is not None:
        lat, lng = branch_at
        await service.add_branch(
            session,
            owner_user_id=owner,
            business_id=business.id,
            address="1 Main Rd",
            state="Tamil Nadu",
            district="Coimbatore",
            pincode=pincode,
            lat=Decimal(str(lat)),
            lng=Decimal(str(lng)),
        )
    return business


async def test_covers_orders_by_branch_distance(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    # 0.09 deg latitude is ~10 km; branches due north of the 641001 centroid
    await _covered_business(db_session, "Far", branch_at=(11.2832, 76.9686))  # ~40 km
    await _covered_business(db_session, "Near", branch_at=(10.9232, 76.9686))  # ~0 km
    await _covered_business(db_session, "Mid", branch_at=(11.0132, 76.9686))  # ~10 km
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Near", "Mid", "Far"]
    assert page.items[0].distance_m < 200
    assert 9_000 < page.items[1].distance_m < 11_000
    assert 39_000 < page.items[2].distance_m < 41_000
    assert page.next_cursor is None


async def test_branchless_business_falls_back_to_primary_pincode(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _covered_business(db_session, "Chennai HQ", primary="600001")  # covers 641001, no branch
    await _covered_business(db_session, "Near", branch_at=(10.9232, 76.9686))
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Near", "Chennai HQ"]
    assert page.items[1].distance_m > 300_000  # Chennai centroid is ~430 km away


async def test_unlocatable_business_sorts_last_with_sentinel(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _covered_business(db_session, "Ghost", primary="999999")  # unknown to geo, no branch
    await _covered_business(db_session, "Near", branch_at=(10.9232, 76.9686))
    page = await covers(db_session, pincode="641001")
    assert [i.name for i in page.items] == ["Near", "Ghost"]
    assert page.items[1].distance_m == UNLOCATABLE_M


async def test_unknown_search_pincode_returns_empty_page(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _covered_business(db_session, "Near", branch_at=(10.9232, 76.9686))
    page = await covers(db_session, pincode="999999")
    assert page.items == []
    assert page.next_cursor is None


async def test_keyset_pages_without_gaps_or_dupes(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    for index, name in enumerate(["A", "B", "C", "D", "E"]):
        await _covered_business(db_session, name, branch_at=(10.9232 + index * 0.02, 76.9686))
    first = await covers(db_session, pincode="641001", limit=2)
    assert [i.name for i in first.items] == ["A", "B"]
    assert first.next_cursor is not None
    second = await covers(db_session, pincode="641001", cursor=first.next_cursor, limit=2)
    assert [i.name for i in second.items] == ["C", "D"]
    assert second.next_cursor is not None
    third = await covers(db_session, pincode="641001", cursor=second.next_cursor, limit=2)
    assert [i.name for i in third.items] == ["E"]
    assert third.next_cursor is None


async def test_equal_distance_ties_break_by_id(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    first = await _covered_business(db_session, "Twin1", branch_at=(10.9232, 76.9686))
    second = await _covered_business(db_session, "Twin2", branch_at=(10.9232, 76.9686))
    page = await covers(db_session, pincode="641001")
    # UUIDv7 ids are time-ordered: creation order is the deterministic tiebreak
    assert [i.id for i in page.items] == [first.id, second.id]


async def test_suspended_and_soft_deleted_excluded(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    keep = await _covered_business(db_session, "Keep", branch_at=(10.9232, 76.9686))
    suspended = await _covered_business(db_session, "Suspended", branch_at=(10.9232, 76.9686))
    suspended.status = "suspended"
    deleted = await _covered_business(db_session, "Deleted", branch_at=(10.9232, 76.9686))
    soft_delete(deleted)
    await db_session.flush()
    page = await covers(db_session, pincode="641001")
    assert [i.id for i in page.items] == [keep.id]


async def test_tampered_cursor_rejected(db_session: AsyncSession, tn_geo_sample: None) -> None:
    with pytest.raises(InvalidCursorError):
        await covers(db_session, pincode="641001", cursor="not-a-cursor")


def test_cursor_roundtrip() -> None:
    last_id = uuid.uuid4()
    assert decode_covers_cursor(encode_covers_cursor(12345, last_id)) == (12345, last_id)
