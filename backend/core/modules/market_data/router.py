"""Market Data module routes (E5).

GET /market/today/{pincode} serves the agri.in home's Today payload in
the frozen A-U2 contract (schemas.py, mirrored in packages/types). The
`agri_today` flag is the single gate: OFF -> 404 feature_disabled and
every Today section is ABSENT from the home's DOM.

A-U2 W1 replaced the weather half with the real Open-Meteo worker
(service.get_weather); W2 replaced mandi with the ingested Agmarknet
rows (service.get_mandi). Calendar and schemes are still A-U1 fixtures
until W3, so `stub` stays True — nothing downstream may mistake a
part-real payload for market truth.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.flags import flag_enabled
from shared.security import SecureRouter

from .fixtures import today_fixture
from .schemas import MandiBlock, TodayPayload
from .service import district_name_for, get_mandi, get_weather
from .weather import now_ist

SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = SecureRouter(prefix="/market", tags=["market_data"])


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
        # A-U2 CP1 proposes contract v2 making `weather` nullable so the
        # two engines fail independently. OWNER DECISION — not taken here.
        raise HTTPException(status_code=503, detail="weather_unavailable")
    weather_block, severe_alert = weather

    # W3 replaces calendar + schemes; until then they are A-U1 fixtures.
    fixture = today_fixture(pincode)

    # Real ingested prices for the visitor's district. None = "no market
    # data for this area yet", which the empty MandiBlock expresses
    # honestly: a market name we do not have, and zero commodities.
    mandi = await get_mandi(session, pincode) or MandiBlock(
        market="", as_of="", source="Agmarknet", commodities=[]
    )

    return TodayPayload(
        pincode=pincode,
        # Real geo, not the fixture's "641* -> Coimbatore" guess.
        district=await district_name_for(session, pincode),
        generated_at=now_ist().isoformat(),
        stub=True,  # flipped to False in W3 when the last fixture goes
        weather=weather_block,
        severe_alert=severe_alert,
        mandi=mandi,
        calendar=fixture.calendar,
        schemes=fixture.schemes,
    )
