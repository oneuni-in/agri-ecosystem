"""M3.C "Recommended" ranking - ORGANIC ONLY.

The ranking fn is the single source of the Recommended label. These tests
lock the non-negotiable: paid signals (subscription_tier, ad campaigns)
must never move the ranking - only verification, ratings, lead response
time and coverage freshness do."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign
from modules.directory import service as directory_service
from modules.directory.milk_home import MilkCard, milk_home
from modules.directory.models import Business
from modules.directory.recommended import RECOMMENDED_LIMIT, rank_recommended
from modules.directory.reviews_models import RatingAggregate

pytestmark = pytest.mark.asyncio


def _card(
    business_id: uuid.UUID, *, verified: bool, tier: str = "free", name: str = "Dairy"
) -> MilkCard:
    return MilkCard(
        id=business_id,
        name=name,
        slug=f"dairy-{business_id.hex[:8]}",
        type="vendor",
        verification_status="verified" if verified else "unverified",
        subscription_tier=tier,
        distance_m=1000,
        lat=None,
        lng=None,
        products=[],
    )


async def _mk_business(session: AsyncSession) -> Business:
    return await directory_service.create_business(
        session,
        owner_user_id=uuid.uuid4(),
        name=f"Dairy {uuid.uuid4().hex[:8]}",
        type_="vendor",
        primary_pincode="641001",
    )


async def test_paid_signals_never_enter_ranking(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """M3.C: two businesses identical on every organic signal keep their
    input (organic) order even when one is premium AND runs a campaign."""
    a = await _mk_business(db_session)
    b = await _mk_business(db_session)
    b.subscription_tier = "premium"
    today = datetime.now(UTC).date()
    db_session.add(
        Campaign(  # paid activity on b - must be invisible to this ranking
            advertiser_business_id=b.id,
            name="paid push",
            status="active",
            budget_display="Rs 1,00,000/mo",
            flight_start=today,
            flight_end=today + timedelta(days=30),
        )
    )
    await db_session.flush()

    ranked = await rank_recommended(
        db_session,
        [_card(a.id, verified=True), _card(b.id, verified=True, tier="premium")],
        now=datetime.now(UTC),
    )
    assert ranked == [a.id, b.id]  # premium + campaign bought nothing


async def test_rating_and_verification_rank(db_session: AsyncSession, tn_geo_sample: None) -> None:
    a = await _mk_business(db_session)  # verified + rated 4.5 x 10
    b = await _mk_business(db_session)  # verified, unrated
    c = await _mk_business(db_session)  # unverified, no signals
    db_session.add(
        RatingAggregate(
            target_type="business",
            target_id=a.id,
            rating_avg=Decimal("4.50"),
            rating_count=10,
        )
    )
    await db_session.flush()

    ranked = await rank_recommended(
        db_session,
        [_card(b.id, verified=True), _card(a.id, verified=True), _card(c.id, verified=False)],
        now=datetime.now(UTC),
    )
    assert ranked[0] == a.id
    assert b.id in ranked
    assert c.id not in ranked  # below MIN_SCORE: bare unverified noise never rails
    assert len(ranked) <= RECOMMENDED_LIMIT


async def test_coverage_freshness_breaks_ties(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """A verified vendor whose coverage was touched in the last 30 days
    outranks an otherwise-identical verified vendor with stale coverage."""
    stale = await _mk_business(db_session)
    fresh = await _mk_business(db_session)
    assert fresh.owner_user_id is not None
    await directory_service.set_coverage(
        db_session,
        owner_user_id=fresh.owner_user_id,
        business_id=fresh.id,
        pincodes=["641001"],
    )
    await db_session.flush()

    ranked = await rank_recommended(
        db_session,
        [_card(stale.id, verified=True), _card(fresh.id, verified=True)],
        now=datetime.now(UTC),
    )
    assert ranked[0] == fresh.id


async def test_empty_cards_empty_result(db_session: AsyncSession) -> None:
    assert await rank_recommended(db_session, [], now=datetime.now(UTC)) == []


async def test_milk_home_carries_recommended_only_unfiltered_first_page(
    db_session: AsyncSession, seed_milk_vendor: Business
) -> None:
    """The rail rides milk_home's covered response - unfiltered first page
    only (chip filters and cursor pages never re-rank)."""
    seed_milk_vendor.verification_status = "verified"
    await db_session.flush()

    result = await milk_home(
        db_session,
        pincode="641001",
        milk_type=None,
        product_category=None,
        cursor=None,
        limit=20,
    )
    assert result.scope == "covered"
    assert [c.id for c in result.recommended] == [seed_milk_vendor.id]

    filtered = await milk_home(
        db_session,
        pincode="641001",
        milk_type="cow",
        product_category=None,
        cursor=None,
        limit=20,
    )
    assert filtered.recommended == []
