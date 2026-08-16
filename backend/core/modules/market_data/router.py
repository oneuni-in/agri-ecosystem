"""Market Data module routes (E5).

GET /market/today/{pincode} serves the agri.in home's Today payload in
the frozen A-U2 contract (schemas.py, mirrored in packages/types). The
`agri_today` flag is the single gate: OFF -> 404 feature_disabled and
every Today section is ABSENT from the home's DOM.

A-U2 W1 replaced the weather half with the real Open-Meteo worker
(service.get_weather). The mandi, calendar and schemes blocks are still
A-U1 fixtures and are replaced by W2/W3; `stub` stays True until the
last one goes, so nothing downstream can mistake a part-real payload
for market truth.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.flags import flag_enabled
from shared.security import SecureRouter

from .fixtures import today_fixture
from .schemas import TodayPayload
from .service import district_name_for, get_weather
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

    # W2/W3 replace these three; until then they are the A-U1 fixtures.
    fixture = today_fixture(pincode)

    return TodayPayload(
        pincode=pincode,
        # Real geo, not the fixture's "641* -> Coimbatore" guess.
        district=await district_name_for(session, pincode),
        generated_at=now_ist().isoformat(),
        stub=True,  # flipped to False in W3 when the last fixture goes
        weather=weather_block,
        severe_alert=severe_alert,
        mandi=fixture.mandi,
        calendar=fixture.calendar,
        schemes=fixture.schemes,
    )
