"""Ads admin surface (D21): campaigns, creatives, placements. NOT flag-gated
- staging while dark (ads_enabled is checked at serve time, Task 8) is
deliberate so staff can build inventory before the module lights up.

Creatives are always created `pending`; approval happens ONLY through the
unified moderation queue (modules/ops/admin_router.py, Task 7 registers the
ads source there) - this router must never flip moderation_status itself.

Every mutation writes an audit entry in the SAME transaction as the change,
then commits, then returns a DTO captured before commit (D12/D16 discipline).
No events publish here - ads CRUD is silent; only creative moderation
decisions emit, and that lands in Task 7."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads import pricing
from modules.ads.models import Campaign, Creative, Placement, RateCardVersion
from modules.ads.schemas import (
    CampaignIn,
    CampaignOut,
    CampaignPageOut,
    CreativeIn,
    CreativeOut,
    CreativePageOut,
    PlacementIn,
    PlacementOut,
    PlacementPageOut,
    PlacementStatusIn,
    RateCardIn,
    RateCardOut,
    StatRowOut,
    StatsOut,
    StatusIn,
    copy_to_json,
)
from modules.ads.service import SLOT_KEYS
from shared import storage
from shared.audit import audit
from shared.db import get_session
from shared.lookups import resolve_business
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError, paginate
from shared.security import SecureRouter, require_role

admin_router = SecureRouter(prefix="/admin/ads", tags=["ads-admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

STAFF = "staff"
SUPER_ADMIN = "super_admin"


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@admin_router.post("/campaigns", status_code=201)
async def create_campaign(request: Request, body: CampaignIn, session: SessionDep) -> CampaignOut:
    admin_id = require_role(request, STAFF, SUPER_ADMIN)
    business = await resolve_business(session, body.advertiser_business_id)
    if business is None:
        raise HTTPException(status_code=422, detail="unknown_business")
    campaign = Campaign(
        advertiser_business_id=body.advertiser_business_id,
        name=body.name,
        budget_display=body.budget_display,
        budget_serves_total=body.budget_serves_total,
        flight_start=body.flight_start,
        flight_end=body.flight_end,
    )
    session.add(campaign)
    await session.flush()
    await audit(
        session,
        action="ads.campaign_created",
        actor_user_id=admin_id,
        target_type="campaign",
        target_id=str(campaign.id),
        metadata={"advertiser_business_id": str(campaign.advertiser_business_id)},
        ip=_ip(request),
    )
    out = CampaignOut.model_validate(campaign)
    await session.commit()
    return out


@admin_router.get("/campaigns")
async def list_campaigns(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> CampaignPageOut:
    require_role(request, STAFF, SUPER_ADMIN)
    try:
        page = await paginate(session, select(Campaign), cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return CampaignPageOut(
        items=[CampaignOut.model_validate(c) for c in page.items], next_cursor=page.next_cursor
    )


@admin_router.post("/campaigns/{campaign_id}/status")
async def set_campaign_status(
    request: Request, campaign_id: uuid.UUID, body: StatusIn, session: SessionDep
) -> CampaignOut:
    admin_id = require_role(request, STAFF, SUPER_ADMIN)
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    campaign.status = body.status
    await session.flush()
    await audit(
        session,
        action="ads.campaign_status_changed",
        actor_user_id=admin_id,
        target_type="campaign",
        target_id=str(campaign.id),
        metadata={"status": campaign.status},
        ip=_ip(request),
    )
    out = CampaignOut.model_validate(campaign)
    await session.commit()
    return out


@admin_router.post("/creatives", status_code=201)
async def create_creative(request: Request, body: CreativeIn, session: SessionDep) -> CreativeOut:
    admin_id = require_role(request, STAFF, SUPER_ADMIN)
    if await session.get(Campaign, body.campaign_id) is None:
        raise HTTPException(status_code=422, detail="unknown_campaign")
    creative = Creative(
        campaign_id=body.campaign_id,
        media_keys=list(body.media_keys),
        copy=copy_to_json(body.ad_copy),
        target_url=body.target_url,
    )
    session.add(creative)  # moderation_status defaults to 'pending' (UGCMixin)
    await session.flush()
    await audit(
        session,
        action="ads.creative_created",
        actor_user_id=admin_id,
        target_type="creative",
        target_id=str(creative.id),
        metadata={
            "campaign_id": str(creative.campaign_id),
            "moderation_status": creative.moderation_status,
        },
        ip=_ip(request),
    )
    out = CreativeOut.model_validate(creative)
    await session.commit()
    return out


@admin_router.get("/creatives")
async def list_creatives(
    request: Request,
    session: SessionDep,
    campaign_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> CreativePageOut:
    require_role(request, STAFF, SUPER_ADMIN)
    query = select(Creative)
    if campaign_id is not None:
        query = query.where(Creative.campaign_id == campaign_id)
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return CreativePageOut(
        items=[CreativeOut.model_validate(c) for c in page.items], next_cursor=page.next_cursor
    )


@admin_router.get("/creatives/{creative_id}/media/{index}")
async def get_creative_media(
    request: Request,
    creative_id: uuid.UUID,
    index: Annotated[int, Path(ge=0)],
    session: SessionDep,
) -> Response:
    require_role(request, STAFF, SUPER_ADMIN)
    creative = await session.get(Creative, creative_id)
    if creative is None or index >= len(creative.media_keys):
        raise HTTPException(status_code=404, detail="creative not found")
    try:
        data = await storage.get_object(creative.media_keys[index])
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    return Response(
        content=data, media_type="image/jpeg", headers={"cache-control": "private, no-store"}
    )


@admin_router.post("/placements", status_code=201)
async def create_placement(
    request: Request, body: PlacementIn, session: SessionDep
) -> PlacementOut:
    admin_id = require_role(request, STAFF, SUPER_ADMIN)
    if body.slot_key not in SLOT_KEYS:
        raise HTTPException(status_code=422, detail="unknown_slot_key")
    if await session.get(Campaign, body.campaign_id) is None:
        raise HTTPException(status_code=422, detail="unknown_campaign")
    placement = Placement(
        campaign_id=body.campaign_id,
        slot_key=body.slot_key,
        geo_target=body.geo_target.model_dump(exclude_none=True),
        weight=body.weight,
    )
    session.add(placement)
    await session.flush()
    await audit(
        session,
        action="ads.placement_created",
        actor_user_id=admin_id,
        target_type="placement",
        target_id=str(placement.id),
        metadata={"campaign_id": str(placement.campaign_id), "slot_key": placement.slot_key},
        ip=_ip(request),
    )
    out = PlacementOut.model_validate(placement)
    await session.commit()
    return out


@admin_router.post("/placements/{placement_id}/status")
async def set_placement_status(
    request: Request, placement_id: uuid.UUID, body: PlacementStatusIn, session: SessionDep
) -> PlacementOut:
    admin_id = require_role(request, STAFF, SUPER_ADMIN)
    placement = await session.get(Placement, placement_id)
    if placement is None:
        raise HTTPException(status_code=404, detail="placement not found")
    placement.status = body.status
    await session.flush()
    await audit(
        session,
        action="ads.placement_status_changed",
        actor_user_id=admin_id,
        target_type="placement",
        target_id=str(placement.id),
        metadata={"status": placement.status},
        ip=_ip(request),
    )
    out = PlacementOut.model_validate(placement)
    await session.commit()
    return out


@admin_router.get("/placements")
async def list_placements(
    request: Request,
    session: SessionDep,
    slot_key: str | None = None,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> PlacementPageOut:
    require_role(request, STAFF, SUPER_ADMIN)
    query = select(Placement)
    if slot_key is not None:
        query = query.where(Placement.slot_key == slot_key)
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return PlacementPageOut(
        items=[PlacementOut.model_validate(p) for p in page.items], next_cursor=page.next_cursor
    )


@admin_router.get("/stats")
async def placement_stats(
    request: Request,
    session: SessionDep,
    placement_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> StatsOut:
    require_role(request, STAFF, SUPER_ADMIN)
    if date_to < date_from or (date_to - date_from).days > 90:
        raise HTTPException(status_code=422, detail="bad_range")
    bounds = {
        "p": placement_id,
        "lo": datetime.combine(date_from, time(0), tzinfo=UTC),
        "hi": datetime.combine(date_to + timedelta(days=1), time(0), tzinfo=UTC),
    }
    rows: dict[date, dict[str, int]] = {}
    for name, table in (("impressions", "ads.impressions"), ("clicks", "ads.clicks")):
        result = await session.execute(
            text(
                f"SELECT (occurred_at AT TIME ZONE 'UTC')::date AS day, count(*) AS n "
                f"FROM {table} WHERE placement_id = :p "
                f"AND occurred_at >= :lo AND occurred_at < :hi GROUP BY day"
            ),
            bounds,
        )
        for day, n in result:
            rows.setdefault(day, {"impressions": 0, "clicks": 0})[name] = n
    return StatsOut(
        rows=[
            StatRowOut(day=d, impressions=v["impressions"], clicks=v["clicks"])
            for d, v in sorted(rows.items())
        ]
    )


# ---------------------------------------------------------------------------
# rate card (M5 Task 3): Ops-editable versioned pricing config. Append-only -
# publishing inserts version N+1, never mutates an existing row (D17
# spec_schemas precedent). The active card is always the newest version
# (pricing.active_rate_card).


@admin_router.get("/rate-card")
async def get_rate_card(request: Request, session: SessionDep) -> RateCardOut:
    require_role(request, STAFF, SUPER_ADMIN)
    try:
        card = await pricing.active_rate_card(session)
    except pricing.RateCardError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc
    return RateCardOut(version=card.version, config=card.config, created_at=card.created_at)


@admin_router.post("/rate-card", status_code=201)
async def publish_rate_card(body: RateCardIn, request: Request, session: SessionDep) -> RateCardOut:
    admin_id = require_role(request, STAFF, SUPER_ADMIN)
    try:
        pricing.validate_rate_card(body.config)
        current = await pricing.active_rate_card(session)
        next_version = current.version + 1
    except pricing.RateCardError as exc:
        if exc.code != "no_rate_card":
            raise HTTPException(status_code=422, detail=exc.code) from exc
        next_version = 1
    card = RateCardVersion(version=next_version, config=body.config, created_by_user_id=admin_id)
    session.add(card)
    try:
        # Savepoint wraps only the insert so a lost race against the
        # UNIQUE(version) index rolls back just this insert, not the
        # caller's transaction (referrals.py / claims.py precedent).
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="version_conflict") from exc
    await audit(
        session,
        action="ads.rate_card_published",
        actor_user_id=admin_id,
        target_type="rate_card",
        target_id=str(card.version),
        metadata={"version": card.version},
        ip=_ip(request),
    )
    out = RateCardOut(version=card.version, config=card.config, created_at=card.created_at)
    await session.commit()
    return out
