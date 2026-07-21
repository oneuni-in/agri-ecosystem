"""Public ads surface (D21): serving + (Task 9) beacons. EVERYTHING here is
gated by the ads_enabled DB flag (404 while dark). Ads are the neutral
monetization: dedicated labeled slots, never pay-to-rank organic - the wire
contract carries label="sponsored" and the component renders the badge
unconditionally (defense in depth on non-negotiable 1). Never log bodies."""

import random
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads import service
from modules.ads.models import Creative, Placement
from modules.ads.schemas import AdServeOut, ServedAdOut
from settings import get_settings
from shared.db import get_session
from shared.flags import flag_enabled
from shared.security import SecureRouter

router = SecureRouter(prefix="/ads", tags=["ads"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_rng = random.Random()  # module-level so tests can monkeypatch/seed it


async def _require_flag(session: AsyncSession) -> None:
    """flag off -> this surface does not exist (404, never 403)."""
    if not await flag_enabled("ads_enabled", session=session):
        raise HTTPException(status_code=404, detail="Not Found")


def _viewer(request: Request, now: datetime) -> str:
    ip = request.client.host if request.client else ""
    return service.viewer_hash(ip, request.headers.get("user-agent", ""), now=now)


@router.get("/serve", public=True)
async def serve(
    request: Request,
    session: SessionDep,
    slot: str,
    pincode: Annotated[str, Query(min_length=6, max_length=6, pattern=r"^\d{6}$")],
    locale: Literal["en", "ta", "hi"] = "en",
) -> AdServeOut:
    await _require_flag(session)
    if slot not in service.SLOT_KEYS:
        raise HTTPException(status_code=422, detail="unknown_slot")
    now = datetime.now(UTC)
    viewer = _viewer(request, now)
    settings = get_settings()
    candidates = await service.eligible_placements(
        session, slot_key=slot, pincode=pincode, today=now.date()
    )
    capped: list[tuple[Placement, Creative]] = []
    for placement, creative in candidates:
        if await service.under_freq_cap(
            viewer, placement.id, cap=settings.ads_freq_cap_per_day, now=now
        ):
            capped.append((placement, creative))
    if not capped:
        return AdServeOut(ad=None)
    placement, creative = service.pick_weighted(capped, _rng)
    try:
        service.validate_target_url(creative.target_url)  # re-check at serve
    except ValueError:
        return AdServeOut(ad=None)  # a bad row must never reach a page
    await service.record_serve(viewer, placement.id, now=now)
    copy = creative.copy.get(locale) or creative.copy.get("en") or {}
    base = settings.media_public_base_url
    return AdServeOut(
        ad=ServedAdOut(
            placement_id=placement.id,
            creative_id=creative.id,
            slot_key=placement.slot_key,
            label="sponsored",
            title=copy.get("title", ""),
            body=copy.get("body", ""),
            media_urls=[f"{base}/{key}" for key in creative.media_keys],
            target_url=creative.target_url,
        )
    )
