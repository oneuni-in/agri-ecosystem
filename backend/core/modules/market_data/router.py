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

import uuid
from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.flags import flag_enabled
from shared.security import SecureRouter

from .alerts import AlertCapReached, list_alerts, subscribe, unsubscribe
from .schemas import (
    CalendarBlock,
    CommodityDetail,
    CommodityListItem,
    MandiBlock,
    SchemesBlock,
    TodayPayload,
    TranslatedText,
)
from .service import (
    district_name_for,
    get_calendar,
    get_commodity,
    get_helplines,
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


# ── price alerts (AG-A16) ────────────────────────────────────────────
# NO public=True here: these read and write a user's own subscriptions,
# so they are private by default on SecureRouter (ADR-0009) and never
# appear in public_routes.txt.


class AlertIn(BaseModel):
    pincode: str = Field(pattern=r"^\d{6}$")


class AlertOut(BaseModel):
    id: uuid.UUID
    pincode: str
    last_notified_on: date | None


def _caller(request: Request) -> uuid.UUID:
    """The authenticated user, from the principal require_auth resolved."""
    user_id = request.state.principal.user_id
    assert isinstance(user_id, uuid.UUID)  # narrow Starlette state's Any
    return user_id


@router.get("/alerts")
async def get_alerts(session: SessionDep, request: Request) -> list[AlertOut]:
    """The CALLER's alerts only — never another user's, and there is no
    parameter that could ask for one."""
    return [
        AlertOut(id=a.id, pincode=a.pincode, last_notified_on=a.last_notified_on)
        for a in await list_alerts(session, _caller(request))
    ]


@router.post("/alerts", status_code=status.HTTP_201_CREATED)
async def create_alert(session: SessionDep, request: Request, body: AlertIn) -> AlertOut:
    """Subscribe to a pincode's daily mandi digest. Idempotent: the home
    card's button has no 'already subscribed' state, so pressing it twice
    must be harmless rather than a 409 the UI has to explain."""
    try:
        alert = await subscribe(session, _caller(request), body.pincode)
    except AlertCapReached:
        raise HTTPException(status_code=429, detail="alert_cap_reached") from None
    return AlertOut(id=alert.id, pincode=alert.pincode, last_notified_on=alert.last_notified_on)


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(session: SessionDep, request: Request, alert_id: uuid.UUID) -> None:
    """Unsubscribe. Someone else's id and a nonexistent id both 404 —
    EXACTLY the same response, so this cannot be used to discover which
    ids exist (the U2 IDOR rule)."""
    if not await unsubscribe(session, _caller(request), alert_id):
        raise HTTPException(status_code=404, detail="alert_not_found")


# ── helplines + schemes (A-U3 W2) ────────────────────────────────────
# public=True: published government helpline numbers and scheme cards —
# public records, already printed on official sites, no user data and no
# mutation. Declared in backend/core/public_routes.txt in this same PR.
#
# NOT flag-gated, like /market/commodities and for the same reason: these
# are their own surfaces (the helpline band, /schemes), and `agri_today`
# is the HOME strip's kill switch, not a switch for the whole module.


class HelplineOut(BaseModel):
    slug: str
    name: TranslatedText
    number: str
    dial: str
    scope: str
    state: str | None
    # Per-number provenance, RENDERED by the UI: a number nobody has
    # re-checked in a year says so on screen.
    source: str
    source_url: str
    verified_on: date


@router.get("/helplines", public=True)
async def get_helpline_list(
    session: SessionDep,
    state: Annotated[str | None, Query(max_length=64)] = None,
) -> list[HelplineOut]:
    """National helplines, plus `state`'s if one is given.

    Uncursored on purpose (the /market/commodities precedent): the set is
    curated and tiny, one row per number a human verified, and it renders
    as a single band rather than a growable list.
    """
    return [
        HelplineOut(
            slug=h.slug,
            name=TranslatedText(**h.name),
            number=h.number,
            dial=h.dial,
            scope=h.scope,
            state=h.state,
            source=h.source,
            source_url=h.source_url,
            verified_on=h.verified_on,
        )
        for h in await get_helplines(session, state)
    ]


@router.get("/schemes", public=True)
async def get_scheme_list(session: SessionDep) -> SchemesBlock:
    """The /schemes listing (A-U3 W2 "schemes static v0").

    The SAME read the home spotlight uses, so the two can never disagree
    about what a scheme says or when it was last verified. Deadlines whose
    `due_on` has passed are already dropped by the service — the page
    never advertises a window that closed.
    """
    return await get_schemes(session)
