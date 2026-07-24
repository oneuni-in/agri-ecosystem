"""Global location context (D19): profile -> GPS -> pincode -> IP -> none.

Server validates every rung against geo tables; GPS/IP are advisory
(THREAT: location spoofing) - nothing here writes state. Authed writes go
through PATCH /identity/profile (pincode), the single location writer.
"""

from typing import Annotated, Literal

from fastapi import Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Profile
from shared.db import get_session
from shared.geo.models import State
from shared.geo.service import district_for_pincode, nearest_pincode
from shared.geoip import state_for_ip
from shared.security import SecureRouter, optional_auth
from shared.security import client_ip as _client_ip

from .schemas import IdentityPublicSchema

location_router = SecureRouter(prefix="/identity/location", tags=["identity"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class LocationOut(IdentityPublicSchema):
    pincode: str | None
    district: str | None
    state: str | None
    source: Literal["profile", "gps", "pincode", "ip", "none"]


async def _context_for_pincode(
    session: AsyncSession, pincode: str, source: Literal["gps", "pincode"]
) -> LocationOut | None:
    district = await district_for_pincode(session, pincode)
    if district is None:
        return None
    state = await session.scalar(select(State).where(State.id == district.state_id))
    return LocationOut(
        pincode=pincode,
        district=district.name,
        state=state.name if state else None,
        source=source,
    )


@location_router.get("", public=True, dependencies=[Depends(optional_auth)])
async def get_location_context(
    request: Request,
    session: SessionDep,
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
    pincode: str | None = Query(default=None, pattern=r"^\d{6}$"),
) -> LocationOut:
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        profile = await session.scalar(select(Profile).where(Profile.user_id == principal.user_id))
        if profile is not None and profile.pincode and profile.district and profile.state:
            return LocationOut(
                pincode=profile.pincode,
                district=profile.district,
                state=profile.state,
                source="profile",
            )
    if lat is not None and lng is not None:
        near = await nearest_pincode(session, lat, lng)
        if near is not None:
            out = await _context_for_pincode(session, near.pincode, "gps")
            if out is not None:
                return out
    if pincode is not None:
        out = await _context_for_pincode(session, pincode, "pincode")
        if out is not None:
            return out
    state_name = state_for_ip(_client_ip(request))
    if state_name is not None:
        return LocationOut(pincode=None, district=None, state=state_name, source="ip")
    return LocationOut(pincode=None, district=None, state=None, source="none")
