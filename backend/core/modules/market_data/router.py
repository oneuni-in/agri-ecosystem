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

from .schemas import CalendarBlock, MandiBlock, TodayPayload, TranslatedText
from .service import (
    district_name_for,
    get_calendar,
    get_mandi,
    get_schemes,
    get_weather,
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

    weather = await get_weather(session, pincode)
    if weather is None:
        # The frozen contract makes `weather` non-nullable, so a payload
        # without it cannot be expressed. 503 -> fetchToday() returns null
        # -> the whole Today block is absent, which is honest but coarse:
        # it also hides mandi, which lives in our own tables and is fine.
        # A-U2 proposes contract v2 making `weather` and `mandi` nullable
        # so the engines fail independently. OWNER DECISION — not taken here.
        raise HTTPException(status_code=503, detail="weather_unavailable")
    weather_block, severe_alert = weather

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
