"""Public ads surface (D21): serving + (Task 9) beacons. EVERYTHING here is
gated by the ads_enabled DB flag (404 while dark). Ads are the neutral
monetization: dedicated labeled slots, never pay-to-rank organic - the wire
contract carries label="sponsored" and the component renders the badge
unconditionally (defense in depth on non-negotiable 1). Never log bodies."""

import random
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads import service
from modules.ads.models import Click, Creative, Impression, Placement
from modules.ads.schemas import AdServeOut, BeaconIn, BeaconOut, ServedAdOut
from settings import get_settings
from shared.cache import get_redis
from shared.db import get_session
from shared.flags import flag_enabled
from shared.geo.service import get_tier
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


def _to_served(placement: Placement, creative: Creative, *, locale: str, base: str) -> ServedAdOut:
    copy = creative.copy.get(locale) or creative.copy.get("en") or {}
    return ServedAdOut(
        placement_id=placement.id,
        creative_id=creative.id,
        slot_key=placement.slot_key,
        label="sponsored",
        title=copy.get("title", ""),
        body=copy.get("body", ""),
        media_urls=[f"{base}/{key}" for key in creative.media_keys],
        target_url=creative.target_url,
    )


@router.get("/serve", public=True)
async def serve(
    request: Request,
    session: SessionDep,
    slot: str,
    pincode: Annotated[str | None, Query(min_length=6, max_length=6, pattern=r"^\d{6}$")] = None,
    locale: Literal["en", "ta", "hi"] = "en",
    category: Annotated[str | None, Query(pattern=r"^[a-z0-9-]{1,40}$")] = None,
    count: Annotated[int, Query(ge=1, le=service.MAX_SERVE_COUNT)] = 1,
) -> AdServeOut:
    """M2: pincode is optional (global slots render before any location is
    known - only geo-untargeted placements match then), `category` narrows to
    category-targeted inventory, `count`>1 feeds the carousel (weighted
    sample without replacement across distinct placements)."""
    await _require_flag(session)
    if slot not in service.SLOT_KEYS:
        raise HTTPException(status_code=422, detail="unknown_slot")
    now = datetime.now(UTC)
    viewer = _viewer(request, now)
    settings = get_settings()
    candidates = await service.eligible_placements(
        session, slot_key=slot, pincode=pincode, category=category, today=now.date()
    )
    tier = await get_tier(session, pincode) if pincode is not None else None
    pool: list[service.Candidate] = []
    for cand in candidates:
        if await service.under_freq_cap(
            viewer, cand.creative.id, cap=settings.ads_freq_cap_per_day, now=now
        ):
            pool.append(cand)
    served: list[ServedAdOut] = []
    dirty = False  # DB writes staged this request (budget decrement / log row)
    while pool and len(served) < count:
        cand = service.pick_weighted(pool, _rng, local_boost=settings.ads_local_boost)
        pool = [c for c in pool if c.placement.id != cand.placement.id]
        try:
            service.validate_target_url(cand.creative.target_url)  # re-check at serve
        except ValueError:
            continue  # a bad row must never reach a page
        if not await service.consume_budget(session, cand.campaign):
            continue  # lost the race for the last credit - never over-serve
        dirty = dirty or cand.campaign.budget_serves_total is not None
        if service.log_delivery(
            session,
            candidate=cand,
            slot_key=slot,
            pincode=pincode,
            category=category,
            viewer=viewer,
            now=now,
            rand=_rng,
            tier=tier,
        ):
            dirty = True
        await service.record_serve(viewer, cand.creative.id, now=now)
        served.append(
            _to_served(
                cand.placement, cand.creative, locale=locale, base=settings.media_public_base_url
            )
        )
    if dirty:
        await session.commit()
    return AdServeOut(ad=served[0] if served else None, ads=served)


@router.post("/impressions", public=True)
async def impression_beacon(body: BeaconIn, request: Request, session: SessionDep) -> BeaconOut:
    return await _track(body, request, session, kind="imp")


@router.post("/clicks", public=True)
async def click_beacon(body: BeaconIn, request: Request, session: SessionDep) -> BeaconOut:
    return await _track(body, request, session, kind="clk")


async def _track(
    body: BeaconIn, request: Request, session: AsyncSession, *, kind: str
) -> BeaconOut:
    await _require_flag(session)
    exists = await session.scalar(select(Placement.id).where(Placement.id == body.placement_id))
    if exists is None:
        raise HTTPException(status_code=404, detail="unknown_placement")
    now = datetime.now(UTC)
    viewer = _viewer(request, now)
    fresh = await get_redis().set(
        f"ads:dedupe:{kind}:{viewer}:{body.placement_id}", "1", nx=True, ex=60
    )
    if not fresh:
        return BeaconOut(status="duplicate")
    model = Impression if kind == "imp" else Click
    session.add(
        model(
            placement_id=body.placement_id,
            creative_id=body.creative_id,
            slot_key=body.slot_key,
            viewer_hash=viewer,
            occurred_at=now,
        )
    )
    await session.commit()
    return BeaconOut(status="ok")
