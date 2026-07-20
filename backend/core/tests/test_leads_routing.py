"""Routing service (D18.B): coverage(pincode) x category business selection.

Non-negotiable #4: an explicit business_id must cover the pincode and be
active, else BusinessNotCoveredError; no business_id means nearest covering
business wins via covers() distance order, category-filtered when given, or
NoCoverageError. Uses pincode 641001 throughout (the D18 mandated pincode).

covers()'s distance anchor needs the searched pincode resolvable in
geo.pincodes (CROSS JOIN, no LEFT fallback for the search side itself) -
verified empirically against test_directory_covers.py's own tn_geo_sample
fixture - so the two auto-route tests pull it in; the explicit-business tests
bypass covers() entirely (raw business_coverage join) and don't need it.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import leads_service, service
from modules.directory.models import Business, Category

pytestmark = pytest.mark.asyncio

PINCODE = "641001"  # non-negotiable 4 mandates this exact pincode


def _owner_of(business: Business) -> uuid.UUID:
    assert business.owner_user_id is not None
    return business.owner_user_id


async def _mk_business(session: AsyncSession, name: str = "Vendor") -> Business:
    owner = uuid.uuid4()
    return await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode=PINCODE
    )


async def _mk_business_with_coverage(
    session: AsyncSession, pincode: str, name: str = "Vendor"
) -> Business:
    business = await _mk_business(session, name)
    await service.set_coverage(
        session, owner_user_id=_owner_of(business), business_id=business.id, pincodes=[pincode]
    )
    return business


async def _category_id(session: AsyncSession, slug: str) -> uuid.UUID:
    category_id = await session.scalar(select(Category.id).where(Category.slug == slug))
    assert category_id is not None, f"seed category missing: {slug}"
    return category_id


async def test_explicit_business_must_cover_pincode(db_session: AsyncSession) -> None:
    covered = await _mk_business_with_coverage(db_session, PINCODE)
    uncovered = await _mk_business(db_session)  # no coverage row for 641001
    routed = await leads_service.route_inquiry(
        db_session, pincode=PINCODE, category=None, business_id=covered.id
    )
    assert routed.id == covered.id
    assert routed.name == covered.name
    assert routed.owner_user_id == covered.owner_user_id
    with pytest.raises(leads_service.BusinessNotCoveredError):
        await leads_service.route_inquiry(
            db_session, pincode=PINCODE, category=None, business_id=uncovered.id
        )


async def test_suspended_business_never_routed(db_session: AsyncSession) -> None:
    covered = await _mk_business_with_coverage(db_session, PINCODE)
    covered.status = "suspended"
    await db_session.flush()
    with pytest.raises(leads_service.BusinessNotCoveredError):
        await leads_service.route_inquiry(
            db_session, pincode=PINCODE, category=None, business_id=covered.id
        )


async def test_auto_route_picks_covering_business(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    covering = await _mk_business_with_coverage(db_session, PINCODE, name="Covering")
    await _mk_business(db_session, name="NotCovering")  # no coverage row for 641001
    routed = await leads_service.route_inquiry(
        db_session, pincode=PINCODE, category=None, business_id=None
    )
    assert routed.id == covering.id
    assert routed.owner_user_id == covering.owner_user_id


async def test_auto_route_filters_by_category(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    dairy_id = await _category_id(db_session, "dairy")
    dairy = await _mk_business_with_coverage(db_session, PINCODE, name="DairyShop")
    await service.assign_categories(
        db_session, owner_user_id=_owner_of(dairy), business_id=dairy.id, category_ids=[dairy_id]
    )
    plain = await _mk_business_with_coverage(db_session, PINCODE, name="PlainShop")
    routed = await leads_service.route_inquiry(
        db_session, pincode=PINCODE, category="dairy", business_id=None
    )
    assert routed.id == dairy.id
    assert routed.id != plain.id


async def test_no_coverage_raises(db_session: AsyncSession) -> None:
    with pytest.raises(leads_service.NoCoverageError):
        await leads_service.route_inquiry(
            db_session, pincode="999999", category=None, business_id=None
        )
