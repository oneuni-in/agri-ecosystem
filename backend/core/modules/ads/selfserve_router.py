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
  - GET  /campaigns/{id}   (read one owned)
  - PATCH /campaigns/{id}  (draft-only, re-quotes)
  - POST /campaigns/{id}/checkout-request | pause | resume  (Task 7)
  - POST /campaigns/{id}/creatives  (Task 8: upload)
  - PATCH /creatives/{id}           (Task 8: edit -> re-moderation)
"""

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Any

import uuid6
from fastapi import Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads import lifecycle, pricing
from modules.ads.models import Campaign, Creative, Placement
from modules.ads.schemas import copy_to_json
from modules.ads.selfserve_schemas import (
    CampaignCreateIn,
    CampaignPatchIn,
    CreativeCopyIn,
    CreativeSnapshotOut,
    MyCampaignOut,
    PlacementSnapshotOut,
    QuoteIn,
    QuoteLineOut,
    QuoteOut,
)
from modules.ads.service import SLOT_KEYS, GeoTargetIn, validate_target_url
from settings import get_settings
from shared import media, storage
from shared.db import get_session
from shared.flags import flag_enabled
from shared.lookups import is_servable, resolve_business, resolve_owned_businesses
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError, Page, paginate
from shared.security import SecureRouter

router = SecureRouter(prefix="/ads/my", tags=["ads-selfserve"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

# Task 8: a creative may be uploaded/edited while the campaign is in any of
# these states - the same set request_checkout/pause/resume already move a
# campaign through, minus the terminal ones (archived/expired/exhausted).
CREATIVE_EDITABLE_STATUSES = frozenset(
    {"draft", "pending_payment", "pending_moderation", "active", "paused"}
)
MAX_CREATIVES_PER_CAMPAIGN = 5
CREATIVE_MEDIA_PREFIX = "ads/"

# Best-effort, once-per-process (catalog_router.py precedent): set on the
# first upload attempt regardless of whether ensure_prefix_public_read
# actually succeeded - that call is itself best-effort.
_media_prefix_ready = False

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


def _check_slot_keys(slot_keys: list[str]) -> None:
    """Wire contract must match the sibling admin route exactly (modules/ads/
    admin_router.create_placement, pinned by tests/test_ads_admin.py): an
    unknown slot key is 422 `detail == "unknown_slot_key"`, a plain string -
    not pydantic's structured error list."""
    if any(slot_key not in SLOT_KEYS for slot_key in slot_keys):
        raise HTTPException(status_code=422, detail="unknown_slot_key")


def _check_geo_target_categories(geo_target: GeoTargetIn) -> None:
    """`categories` is a top-level wizard field (see _merge_geo_target); a
    client-supplied `geo_target.categories` would be silently clobbered by
    it, which is an ambiguous wire contract - reject it outright instead."""
    if geo_target.categories:
        raise HTTPException(status_code=422, detail="categories_in_geo_target")


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


def _quote_snapshot(quote: pricing.Quote) -> dict[str, Any]:
    """The itemized quote persisted onto `Campaign.quote` at create/patch
    re-quote time (money-path review 2b) - line items + rates, not just the
    4-number decomposition already on the scalar columns. Handed to billing
    verbatim via shared.lookups.CampaignBillingRef.quote for invoice
    provenance; JSONB-ready (lines as 2-element [label, amount_paise] lists,
    not the QuoteLine dataclass)."""
    return {
        "lines": [[line.label, line.amount_paise] for line in quote.lines],
        "pricing_model": quote.pricing_model,
        "tier": quote.tier,
        "multiplier_bp": quote.multiplier_bp,
        "serves_total": quote.serves_total,
        "weeks": quote.weeks,
        "rate_card_version": quote.rate_card_version,
        "gst_rate_bp": get_settings().gst_rate_bp,
        "subtotal_paise": quote.subtotal_paise,
        "gst_paise": quote.gst_paise,
        "total_paise": quote.total_paise,
    }


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
        display_status=lifecycle.display_status(campaign, today=datetime.now(UTC).date()),
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


async def _ensure_public_media() -> None:
    global _media_prefix_ready
    if _media_prefix_ready:
        return
    await storage.ensure_prefix_public_read(CREATIVE_MEDIA_PREFIX)
    _media_prefix_ready = True


def _parse_copy_json(copy_json: str) -> dict[str, dict[str, str]]:
    """Multipart `copy_json` -> validated `{locale: {title, body}}`, JSONB-
    ready (CreativeCopyIn reuses CreativeIn's exact locale rules - see
    modules/ads/selfserve_schemas.py). Any failure - bad JSON, an unknown
    locale key, a missing `en` block, an over-length title/body - collapses
    to the SAME wire error, `invalid_copy_json`: the client only needs to
    know "fix your copy payload", not which specific rule tripped."""
    try:
        raw = json.loads(copy_json)
        parsed = CreativeCopyIn.model_validate(raw)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="invalid_copy_json") from exc
    return copy_to_json(parsed.root)


def _validated_target_url(target_url: str) -> str:
    try:
        validate_target_url(target_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid_target_url") from exc
    return target_url


async def _upload_creative_image(file: UploadFile) -> str:
    """Catalog upload pattern verbatim (modules/directory/catalog_router.py
    ::upload_product_image) - never fork the media helper (check_media_fork
    lint gate)."""
    data = await file.read(media.MAX_IMAGE_BYTES + 1)
    try:
        jpeg, _ = media.reencode_image(data)
    except media.MediaError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    key = f"{CREATIVE_MEDIA_PREFIX}{uuid6.uuid7().hex}.jpg"
    await _ensure_public_media()  # once-per-process, best-effort
    try:
        await storage.put_object(key, jpeg, "image/jpeg")  # storage before DB (avatar precedent)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    return key


async def _owned_creative(
    session: AsyncSession, user_id: uuid.UUID, creative_id: uuid.UUID
) -> tuple[Creative, Campaign]:
    """IDOR guard (NN4 twin): a creative that doesn't exist and a creative
    that exists but belongs to someone else's campaign must be
    indistinguishable - both 404, never 403 (`_owned_campaign` itself
    enforces the ownership half once the creative's campaign is known)."""
    creative = await session.get(Creative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="Not Found")
    campaign = await _owned_campaign(session, user_id, creative.campaign_id)
    return creative, campaign


# ---------------------------------------------------------------------------
# POST /quote


@router.post("/quote")
async def quote_campaign(body: QuoteIn, session: SessionDep) -> QuoteOut:
    await _require_flag(session)
    _check_slot_keys(body.slot_keys)
    _check_geo_target_categories(body.geo_target)
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
    _check_slot_keys(body.slot_keys)
    _check_geo_target_categories(body.geo_target)
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
        quote=_quote_snapshot(quote),
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
    if body.geo_target is not None:
        _check_geo_target_categories(body.geo_target)
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
        campaign.quote = _quote_snapshot(quote)

        merged_geo = _merge_geo_target(new_geo_target, new_categories)
        for placement in placements:
            placement.geo_target = merged_geo

    await session.flush()
    out = _campaign_out(campaign, placements, creatives)
    await session.commit()
    return out


# ---------------------------------------------------------------------------
# POST /campaigns/{id}/checkout-request  (Task 7: draft -> pending_payment)


@router.post("/campaigns/{campaign_id}/checkout-request")
async def request_checkout(
    campaign_id: uuid.UUID, request: Request, session: SessionDep
) -> MyCampaignOut:
    """Task 9's billing checkout route requires the campaign to already be
    `pending_payment` before it will talk to Razorpay - this is the only way
    a draft gets there."""
    await _require_flag(session)
    user_id = _principal_user_id(request)
    campaign = await _owned_campaign(session, user_id, campaign_id)
    try:
        await lifecycle.request_checkout(session, campaign)
    except lifecycle.LifecycleError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    placements, creatives = await _placements_and_creatives(session, campaign.id)
    out = _campaign_out(campaign, placements, creatives)
    await session.commit()
    return out


# ---------------------------------------------------------------------------
# POST /campaigns/{id}/pause  (Task 7: active -> paused)


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: uuid.UUID, request: Request, session: SessionDep
) -> MyCampaignOut:
    await _require_flag(session)
    user_id = _principal_user_id(request)
    campaign = await _owned_campaign(session, user_id, campaign_id)
    if campaign.status != "active":
        raise HTTPException(status_code=409, detail="not_active")
    campaign.status = "paused"
    await session.flush()
    placements, creatives = await _placements_and_creatives(session, campaign.id)
    out = _campaign_out(campaign, placements, creatives)
    await session.commit()
    return out


# ---------------------------------------------------------------------------
# POST /campaigns/{id}/resume  (Task 7: paused -> active | pending_moderation)


@router.post("/campaigns/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: uuid.UUID, request: Request, session: SessionDep
) -> MyCampaignOut:
    """Re-runs the activation gate rather than jumping straight back to
    active: a refunded-then-resumed campaign (paid_at untouched, budget
    zeroed by lifecycle.on_payment_event) or one whose creative was demoted
    mid-pause both need to land back in pending_moderation, not active.

    A campaign whose business was paused by staff enforcement
    (pause_campaigns_for_business) must not be un-paused by its owner just
    by hitting this route - is_servable is the same fail-closed M1.5.E
    check the serve path itself uses."""
    await _require_flag(session)
    user_id = _principal_user_id(request)
    campaign = await _owned_campaign(session, user_id, campaign_id)
    if campaign.status != "paused":
        raise HTTPException(status_code=409, detail="not_paused")
    if campaign.flight_end < datetime.now(UTC).date():
        raise HTTPException(status_code=409, detail="flight_over")
    if not await is_servable(session, campaign.advertiser_business_id):
        raise HTTPException(status_code=409, detail="business_not_servable")
    if not await lifecycle.maybe_activate(session, campaign):
        campaign.status = "pending_moderation"
        await session.flush()
    placements, creatives = await _placements_and_creatives(session, campaign.id)
    out = _campaign_out(campaign, placements, creatives)
    await session.commit()
    return out


# ---------------------------------------------------------------------------
# POST /campaigns/{id}/creatives  (Task 8: self-serve creative upload)


@router.post("/campaigns/{campaign_id}/creatives", status_code=201)
async def create_creative(
    campaign_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    copy_json: Annotated[str, Form()],
    target_url: Annotated[str, Form()],
    file: Annotated[UploadFile | None, File(description="creative image (jpeg/png/webp)")] = None,
) -> CreativeSnapshotOut:
    await _require_flag(session)
    user_id = _principal_user_id(request)
    campaign = await _owned_campaign(session, user_id, campaign_id)
    if campaign.status not in CREATIVE_EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail="not_editable")

    existing_count = await session.scalar(
        select(func.count()).select_from(Creative).where(Creative.campaign_id == campaign.id)
    )
    if (existing_count or 0) >= MAX_CREATIVES_PER_CAMPAIGN:
        raise HTTPException(status_code=409, detail="creative_limit")

    ad_copy = _parse_copy_json(copy_json)
    url = _validated_target_url(target_url)
    media_keys = [await _upload_creative_image(file)] if file is not None else []

    creative = Creative(
        campaign_id=campaign.id,
        media_keys=media_keys,
        copy=ad_copy,
        target_url=url,
    )
    session.add(creative)  # moderation_status defaults to 'pending' (UGCMixin)
    await session.flush()
    out = _creative_snapshot(creative, get_settings().media_public_base_url)
    await session.commit()
    return out


# ---------------------------------------------------------------------------
# PATCH /creatives/{id}  (Task 8: edit -> re-moderation, edit-after-approve
# bypass threat)


@router.patch("/creatives/{creative_id}")
async def patch_creative(
    creative_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    copy_json: Annotated[str | None, Form()] = None,
    target_url: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File(description="creative image (jpeg/png/webp)")] = None,
) -> CreativeSnapshotOut:
    """ANY content change (copy, link, or a replacement image) re-pends the
    creative and, when the campaign is currently `active`, demotes it back
    to `pending_moderation` in the SAME transaction
    (lifecycle.demote_to_moderation is a documented no-op off `active`, so
    calling it unconditionally on a real change is safe and simpler than
    branching on campaign.status here) - closing the edit-after-approve
    bypass: an advertiser must never be able to swap in unapproved content
    behind the moderation queue's back while the old, approved content keeps
    serving."""
    await _require_flag(session)
    user_id = _principal_user_id(request)
    creative, campaign = await _owned_creative(session, user_id, creative_id)
    if campaign.status not in CREATIVE_EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail="not_editable")

    changed = False
    if copy_json is not None:
        creative.copy = _parse_copy_json(copy_json)
        changed = True
    if target_url is not None:
        creative.target_url = _validated_target_url(target_url)
        changed = True
    if file is not None:
        creative.media_keys = [await _upload_creative_image(file)]  # JSONB: reassign, never mutate
        changed = True

    if changed:
        creative.moderation_status = "pending"
        await lifecycle.demote_to_moderation(session, campaign)

    await session.flush()
    out = _creative_snapshot(creative, get_settings().media_public_base_url)
    await session.commit()
    return out
