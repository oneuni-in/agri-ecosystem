"""Market Data module routes (E5).

A-U1 W3: one STUB-UNTIL-A-U2 endpoint. GET /market/today/{pincode} returns
the agri.in home's Today payload in the frozen A-U2 production shape
(schemas.py, mirrored in packages/types). The `agri_today` flag is the
single gate: OFF (prod default) → 404 feature_disabled and every Today
section on the home is ABSENT from the DOM; ON (dev/e2e) → deterministic
fixtures. A-U2 (D42–44) replaces fixtures.py with real workers WITHOUT
touching this contract or the UI.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.flags import flag_enabled
from shared.security import SecureRouter

from .fixtures import today_fixture
from .schemas import TodayPayload

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
    return today_fixture(pincode)
