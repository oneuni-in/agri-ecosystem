"""Advertiser self-serve campaign API (M5 Task 6): quote -> create draft ->
read/list -> patch. EVERYTHING here is gated by the ads_enabled DB flag (404
while dark, same as modules/ads/router.py) and every read/write is scoped to
the caller's OWNED businesses (NN4 - campaign IDOR is the point of this
router: not-yours == not-found, 404 never 403).

Sections below, in the order Tasks 7/8/13 slot into:
  - helpers (flag gate, principal, ownership guard, DTO builders)
  - POST /quote            (price a not-yet-created campaign)
  - POST /campaigns        (create a draft)
  - GET  /campaigns        (list owned)
  - GET  /campaigns/{id}   (read one owned)      <- Task 8 adds creative reads here
  - PATCH /campaigns/{id}  (draft-only, re-quotes) <- Task 7 adds pause/resume/submit
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads import pricing
from modules.ads.models import Campaign, Creative, Placement
from modules.ads.selfserve_schemas import (
    CampaignCreateIn,
    CampaignPatchIn,
    CreativeSnapshotOut,
    MyCampaignOut,
    PlacementSnapshotOut,
    QuoteIn,
    QuoteLineOut,
    QuoteOut,
)
from modules.ads.service import GeoTargetIn
from settings import get_settings
from shared.db import get_session
from shared.flags import flag_enabled
from shared.lookups import resolve_business, resolve_owned_businesses
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError, Page, paginate
from shared.security import SecureRouter

router = SecureRouter(prefix="/ads/my", tags=["ads-selfserve"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

# ---------------------------------------------------------------------------
# helpers


async def _require_flag(session: AsyncSession) -> None:
    """flag off -> this surface does not exist (404, never 403)."""
    if not await flag_enabled("ads_enabled", session=session):
        raise HTTPException(status_code=404, detail="Not Found")


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    return uuid.UUID(str(principal.user_id))


async def _owned_campaign(
    session: AsyncSession, user_id: uuid.UUID, campaign_id: uuid.UUID
) -> Campaign:
    """IDOR guard (NN4): not-yours == not-found (404, never 403). Used by
    EVERY campaign read/write in this router."""
    campaign = await session.get(Campaign, campaign_id)
    if campaign is not None:
        ref = await resolve_business(session, campaign.advertiser_business_id)
        if ref is not None and ref.owner_user_id == user_id:
            return campaign
    raise HTTPException(status_code=404, detail="Not Found")


def _merge_geo_target(geo_target: GeoTargetIn, categories: list[str] | None) -> dict[str, object]:
    """Categories are a top-level wizard field but live INSIDE
    Placement.geo_target on the wire/storage side. Drop None/empty keys so an
    all-default GeoTargetIn + no categories stays `{}` (= serve everywhere)."""
    merged: dict[str, object] = {
        **geo_target.model_dump(exclude_none=True),
        "categories": categories or None,
    }
    return {key: value for key, value in merged.items() if value}


def _quote_out(quote: pricing.Quote) -> QuoteOut:
    return QuoteOut(
        pricing_model=quote.pricing_model,
        tier=quote.tier,
        multiplier_bp=quote.multiplier_bp,
        serves_total=quote.serves_total,
        weeks=quote.weeks,
        lines=[
            QuoteLineOut(label=line.label, amount_paise=line.amount_paise) for line in quote.lines
        ],
        subtotal_paise=quote.subtotal_paise,
        gst_paise=quote.gst_paise,
        total_paise=quote.total_paise,
        rate_card_version=quote.rate_card_version,
    )


def _creative_snapshot(creative: Creative, media_base: str) -> CreativeSnapshotOut:
    return CreativeSnapshotOut(
        id=creative.id,
        copy=creative.copy,
        media_urls=[f"{media_base}/{key}" for key in creative.media_keys],
        target_url=creative.target_url,
        moderation_status=creative.moderation_status,
    )


def _campaign_out(
    campaign: Campaign, placements: Sequence[Placement], creatives: Sequence[Creative]
) -> MyCampaignOut:
    media_base = get_settings().media_public_base_url
    return MyCampaignOut(
        id=campaign.id,
        advertiser_business_id=campaign.advertiser_business_id,
        name=campaign.name,
        status=campaign.status,
        display_status=campaign.status,  # Task 7 replaces with the real derivation
        pricing_model=campaign.pricing_model,
        price_paise=campaign.price_paise,
        price_subtotal_paise=campaign.price_subtotal_paise,
        price_gst_paise=campaign.price_gst_paise,
        rate_card_version=campaign.rate_card_version,
        budget_serves_total=campaign.budget_serves_total,
        budget_serves_used=campaign.budget_serves_used,
        daily_serve_cap=campaign.daily_serve_cap,
        flight_start=campaign.flight_start,
        flight_end=campaign.flight_end,
        created_at=campaign.created_at,
        placements=[
            PlacementSnapshotOut(
                id=p.id, slot_key=p.slot_key, geo_target=p.geo_target, status=p.status
            )
            for p in placements
        ],
        creatives=[_creative_snapshot(c, media_base) for c in creatives],
    )


async def _placements_and_creatives(
    session: AsyncSession, campaign_id: uuid.UUID
) -> tuple[Sequence[Placement], Sequence[Creative]]:
    placements = (
        await session.scalars(
            select(Placement).where(Placement.campaign_id == campaign_id).order_by(Placement.id)
        )
    ).all()
    creatives = (
        await session.scalars(
            select(Creative).where(Creative.campaign_id == campaign_id).order_by(Creative.id)
        )
    ).all()
    return placements, creatives


# ---------------------------------------------------------------------------
# POST /quote


@router.post("/quote")
async def quote_campaign(body: QuoteIn, session: SessionDep) -> QuoteOut:
    await _require_flag(session)
    try:
        quote = await pricing.quote_campaign(
            session,
            slot_keys=body.slot_keys,
            geo_target=body.geo_target.model_dump(exclude_none=True),
            categories=body.categories,
            flight_start=body.flight_start,
            flight_end=body.flight_end,
            serves_total=body.serves_total,
        )
    except pricing.RateCardError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    return _quote_out(quote)


# ---------------------------------------------------------------------------
# POST /campaigns


@router.post("/campaigns", status_code=201)
async def create_campaign(
    body: CampaignCreateIn, request: Request, session: SessionDep
) -> MyCampaignOut:
    await _require_flag(session)
    user_id = _principal_user_id(request)
    ref = await resolve_business(session, body.business_id)
    if ref is None or ref.owner_user_id != user_id:
        # not-yours == not-found: ownership must not be an oracle (NN4)
        raise HTTPException(status_code=404, detail="Not Found")

    try:
        quote = await pricing.quote_campaign(
            session,
            slot_keys=body.slot_keys,
            geo_target=body.geo_target.model_dump(exclude_none=True),
            categories=body.categories,
            flight_start=body.flight_start,
            flight_end=body.flight_end,
            serves_total=body.serves_total,
        )
    except pricing.RateCardError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc

    campaign = Campaign(
        advertiser_business_id=body.business_id,
        name=body.name,
        status="draft",
        budget_display="",
        pricing_model=quote.pricing_model,
        price_paise=quote.total_paise,
        price_subtotal_paise=quote.subtotal_paise,
        price_gst_paise=quote.gst_paise,
        rate_card_version=quote.rate_card_version,
        budget_serves_total=quote.serves_total,
        daily_serve_cap=body.daily_serve_cap,
        flight_start=body.flight_start,
        flight_end=body.flight_end,
    )
    session.add(campaign)
    await session.flush()

    merged_geo = _merge_geo_target(body.geo_target, body.categories)
    placements = [
        Placement(campaign_id=campaign.id, slot_key=slot_key, geo_target=merged_geo, weight=1)
        for slot_key in body.slot_keys
    ]
    session.add_all(placements)
    await session.flush()

    out = _campaign_out(campaign, placements, [])
    await session.commit()
    return out


# ---------------------------------------------------------------------------
# GET /campaigns


@router.get("/campaigns")
async def list_campaigns(
    request: Request,
    session: SessionDep,
    business_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> Page[MyCampaignOut]:
    await _require_flag(session)
    user_id = _principal_user_id(request)
    owned_ids = {ref.id for ref in await resolve_owned_businesses(session, user_id)}

    if business_id is not None:
        if business_id not in owned_ids:
            raise HTTPException(status_code=404, detail="Not Found")
        target_ids: list[uuid.UUID] = [business_id]
    else:
        target_ids = list(owned_ids)

    if not target_ids:
        return Page(items=[], next_cursor=None)

    query = select(Campaign).where(Campaign.advertiser_business_id.in_(target_ids))
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc

    items = []
    for campaign in page.items:
        placements, creatives = await _placements_and_creatives(session, campaign.id)
        items.append(_campaign_out(campaign, placements, creatives))
    return Page(items=items, next_cursor=page.next_cursor)


# ---------------------------------------------------------------------------
# GET /campaigns/{id}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: uuid.UUID, request: Request, session: SessionDep
) -> MyCampaignOut:
    await _require_flag(session)
    user_id = _principal_user_id(request)
    campaign = await _owned_campaign(session, user_id, campaign_id)
    placements, creatives = await _placements_and_creatives(session, campaign.id)
    return _campaign_out(campaign, placements, creatives)


# ---------------------------------------------------------------------------
# PATCH /campaigns/{id}

_REPRICE_FIELDS = {"geo_target", "categories", "flight_start", "flight_end", "serves_total"}


@router.patch("/campaigns/{campaign_id}")
async def patch_campaign(
    campaign_id: uuid.UUID, body: CampaignPatchIn, request: Request, session: SessionDep
) -> MyCampaignOut:
    await _require_flag(session)
    user_id = _principal_user_id(request)
    campaign = await _owned_campaign(session, user_id, campaign_id)
    if campaign.status != "draft":
        raise HTTPException(status_code=409, detail="not_editable")

    sent = body.model_fields_set
    placements, creatives = await _placements_and_creatives(session, campaign.id)

    if "name" in sent and body.name is not None:
        campaign.name = body.name
    if "daily_serve_cap" in sent:
        campaign.daily_serve_cap = body.daily_serve_cap

    if sent & _REPRICE_FIELDS:
        current_geo = dict(placements[0].geo_target) if placements else {}
        current_categories = current_geo.pop("categories", None)
        new_geo_target = (
            body.geo_target
            if "geo_target" in sent and body.geo_target is not None
            else GeoTargetIn(**current_geo)
        )
        new_categories = body.categories if "categories" in sent else current_categories
        new_flight_start = (
            body.flight_start
            if "flight_start" in sent and body.flight_start is not None
            else campaign.flight_start
        )
        new_flight_end = (
            body.flight_end
            if "flight_end" in sent and body.flight_end is not None
            else campaign.flight_end
        )
        new_serves_total = (
            body.serves_total if "serves_total" in sent else campaign.budget_serves_total
        )
        if new_flight_start >= new_flight_end:
            raise HTTPException(status_code=422, detail="invalid_flight_range")

        try:
            quote = await pricing.quote_campaign(
                session,
                slot_keys=[p.slot_key for p in placements],
                geo_target=new_geo_target.model_dump(exclude_none=True),
                categories=new_categories or [],
                flight_start=new_flight_start,
                flight_end=new_flight_end,
                serves_total=new_serves_total,
            )
        except pricing.RateCardError as exc:
            raise HTTPException(status_code=422, detail=exc.code) from exc

        campaign.pricing_model = quote.pricing_model
        campaign.price_paise = quote.total_paise
        campaign.price_subtotal_paise = quote.subtotal_paise
        campaign.price_gst_paise = quote.gst_paise
        campaign.rate_card_version = quote.rate_card_version
        campaign.budget_serves_total = quote.serves_total
        campaign.flight_start = new_flight_start
        campaign.flight_end = new_flight_end

        merged_geo = _merge_geo_target(new_geo_target, new_categories)
        for placement in placements:
            placement.geo_target = merged_geo

    await session.flush()
    out = _campaign_out(campaign, placements, creatives)
    await session.commit()
    return out
