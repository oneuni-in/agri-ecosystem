"""A-U6: the two fields the agri category landing added to `covers()`.

`contact_branch_id` — an ID, so a list card can run D18's reveal. The test
that matters is the one asserting no NUMBER travels with it.

`recommended` — the M3.C organic label, now on the directory read as well as
milk-home. The invariant carried over with it: paid signals cannot buy it.
"""

import uuid
from dataclasses import asdict
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.covers import covers
from modules.directory.models import Business
from modules.directory.schemas import CoversItemOut

pytestmark = pytest.mark.asyncio


async def _covered_business(
    session: AsyncSession,
    name: str,
    *,
    verified: bool = False,
    tier: str = "free",
    branch_at: tuple[float, float] | None = (10.9232, 76.9686),
    phone: str | None = None,
    whatsapp: str | None = None,
    pincode: str = "641001",
) -> Business:
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode=pincode
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
            phone=phone,
            whatsapp=whatsapp,
        )
    if verified:
        business.verification_status = "verified"
    if tier != "free":
        business.subscription_tier = tier
    await session.flush()
    return business


async def test_contact_branch_id_is_the_branch_that_has_a_number(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _covered_business(db_session, "Reachable", phone="+919000000001")
    page = await covers(db_session, pincode="641001")
    item = next(i for i in page.items if i.name == "Reachable")
    assert item.contact_branch_id is not None


async def test_contact_branch_id_is_none_without_a_number(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """A listing with no number must not grow a Call button that cannot dial."""
    await _covered_business(db_session, "Silent")
    page = await covers(db_session, pincode="641001")
    item = next(i for i in page.items if i.name == "Silent")
    assert item.contact_branch_id is None


async def test_whatsapp_only_branch_still_reachable(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _covered_business(db_session, "WaOnly", whatsapp="+919000000002")
    page = await covers(db_session, pincode="641001")
    item = next(i for i in page.items if i.name == "WaOnly")
    assert item.contact_branch_id is not None


async def test_ungeocoded_branch_still_yields_a_contact_branch(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """`nb` (the distance anchor) is geocoded-only; the contact lateral is not.
    A business whose only branch lacks coordinates still has a phone worth
    revealing, and must not lose its Call button to a missing lat/lng."""
    owner = uuid.uuid4()
    business = await service.create_business(
        session=db_session,
        owner_user_id=owner,
        name="NoCoords",
        type_="vendor",
        primary_pincode="641001",
    )
    await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id, pincodes=["641001"]
    )
    await service.add_branch(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        address="2 Main Rd",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode="641001",
        phone="+919000000003",
    )
    page = await covers(db_session, pincode="641001")
    item = next(i for i in page.items if i.name == "NoCoords")
    assert item.contact_branch_id is not None


async def test_covers_payload_carries_no_contact_details(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """THE contract. D18.C: numbers never travel in a list payload. The card
    gets an id and nothing else — only POST /branches/{id}/reveal, which is
    login-gated, daily-capped and DPDP-logged, returns a number."""
    await _covered_business(
        db_session, "Reachable", phone="+919000000001", whatsapp="+919000000001"
    )
    page = await covers(db_session, pincode="641001")
    item = next(i for i in page.items if i.name == "Reachable")

    fields = asdict(item)
    assert "phone" not in fields
    assert "whatsapp" not in fields
    serialised = CoversItemOut(**fields).model_dump_json()
    assert "9000000001" not in serialised
    # The wire schema itself must not grow a number-shaped field later.
    assert "phone" not in CoversItemOut.model_fields
    assert "whatsapp" not in CoversItemOut.model_fields


async def test_recommended_defaults_false_on_the_wire(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """`covers()` does not score — the route does. An unranked payload means
    "no badge", never a crash, so every existing consumer is unaffected."""
    await _covered_business(db_session, "Plain")
    page = await covers(db_session, pincode="641001")
    item = next(i for i in page.items if i.name == "Plain")
    assert CoversItemOut(**asdict(item)).recommended is False


async def test_paid_signals_never_enter_the_covers_recommended_label(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """M3.C carried onto the directory read: premium buys placement in the
    covers SORT (tier_rank, by design and separately tested) but must never
    buy the Recommended LABEL. Two identical businesses, one premium: the
    ranking must not separate them."""
    from datetime import UTC, datetime

    from modules.directory.recommended import rank_recommended

    free = await _covered_business(db_session, "FreeCo", verified=True)
    paid = await _covered_business(db_session, "PaidCo", verified=True, tier="premium")
    page = await covers(db_session, pincode="641001")
    ranked = set(await rank_recommended(db_session, page.items, now=datetime.now(UTC)))
    assert (free.id in ranked) == (paid.id in ranked)
