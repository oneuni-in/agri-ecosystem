"""Market Data module routes (E5).

GET /market/today/{pincode} serves the agri.in home's Today payload in
the frozen A-U2 contract (schemas.py, mirrored in packages/types).

A-U2 completed the fixture replacement: weather comes from Open-Meteo
(W1), mandi from ingested Agmarknet rows (W2), and schemes, deadlines and
the crop calendar from the E5 dataset tables (W3, migration 0039).
`market_data/fixtures.py` is gone and `stub` is now permanently False —
nothing in this payload is invented.

The `agri_today` flag remains the single gate and is now ON by default
(0040). It stays in place as a kill switch: flipping it off 404s the
endpoint, and every Today section vanishes from the home's DOM rather
than rendering an empty shell.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.flags import flag_enabled
from shared.security import SecureRouter

from .schemas import (
    CalendarBlock,
    CommodityDetail,
    CommodityListItem,
    MandiBlock,
    TodayPayload,
    TranslatedText,
)
from .service import (
    district_name_for,
    get_calendar,
    get_commodity,
    get_mandi,
    get_schemes,
    get_weather,
    list_commodities,
)
from .weather import now_ist

SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = SecureRouter(prefix="/market", tags=["market_data"])

# Rendered when no zone claims the visitor's district. An empty strip is
# the honest shape: the section shows its heading and nothing else, which
# is what "we have not written a calendar for your area" looks like.
_EMPTY_ZONE = TranslatedText(en="", ta="", hi="")


# public=True: read-only reference data (same class as /catalog/verticals);
# registered in backend/core/public_routes.txt in this same PR.
@router.get("/today/{pincode}", public=True)
async def get_today(
    session: SessionDep,
    pincode: Annotated[str, Path(min_length=6, max_length=6, pattern=r"^\d{6}$")],
) -> TodayPayload:
    # Flag consumed at the API boundary (A-U1 contract): the frontend never
    # reads flags — an absent endpoint IS the off state.
    if not await flag_enabled("agri_today", session=session):
        raise HTTPException(status_code=404, detail="feature_disabled")

    # Contract v2: weather is nullable, so an upstream outage with a cold
    # cache costs the weather section and nothing else. mandi and the
    # calendar keep serving from our own tables.
    weather = await get_weather(session, pincode)
    weather_block, severe_alert = weather if weather is not None else (None, None)

    # Real ingested prices for the visitor's district. None = "no market
    # data for this area yet", which the empty MandiBlock expresses
    # honestly: a market name we do not have, and zero commodities.
    mandi = await get_mandi(session, pincode) or MandiBlock(
        market="", as_of="", source="Agmarknet", commodities=[]
    )

    calendar = await get_calendar(session, pincode) or CalendarBlock(
        zone=_EMPTY_ZONE, months=[], sowing=[], harvesting=[]
    )

    return TodayPayload(
        pincode=pincode,
        # Real geo, not the fixture's "641* -> Coimbatore" guess.
        district=await district_name_for(session, pincode),
        generated_at=now_ist().isoformat(),
        # Every block above is real data now. The field stays in the frozen
        # contract (removing it would be a contract change) and is pinned
        # False so no surface can be told this is fixture output again.
        stub=False,
        weather=weather_block,
        severe_alert=severe_alert,
        mandi=mandi,
        calendar=calendar,
        schemes=await get_schemes(session),
    )


# public=True: the same read-only reference class as /market/today — public
# records with no user data and no mutation. Declared in
# backend/core/public_routes.txt in this same PR.
#
# NOT flag-gated, deliberately. `agri_today` gates the HOME's Today strip,
# which was the A-U1 contract; these are their own pages and their own
# surface. Turning the home strip off as a kill switch should not also
# delete a set of indexed SEO pages out from under Google.
@router.get("/commodities", public=True)
async def get_commodities(session: SessionDep) -> list[CommodityListItem]:
    """Curated commodities that have servable prices.

    Not cursor-paginated because it cannot grow unboundedly: it returns at
    most one row per CURATED commodity (eight today, and each one is a
    hand-written editorial entry, not user- or feed-created). The list
    endpoints the pagination rule exists for are the ones a feed can grow
    without limit — market.price_rows is one, and it is never exposed
    whole.
    """
    return await list_commodities(session)


@router.get("/commodities/{slug}", public=True)
async def get_commodity_detail(
    session: SessionDep,
    slug: Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")],
) -> CommodityDetail:
    """One commodity across every market that reported it in 30 days.

    404 when the commodity is uncurated OR has no servable rows: a page
    with no data must not exist rather than exist empty (the ISR page
    self-noindexes on the same signal).
    """
    detail = await get_commodity(session, slug)
    if detail is None:
        raise HTTPException(status_code=404, detail="commodity_not_found")
    return detail
