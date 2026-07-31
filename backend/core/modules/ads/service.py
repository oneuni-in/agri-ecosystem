"""Ads service (D21): validation + (Task 8) serving eligibility."""

import hashlib
import random
import re
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign, Creative, Placement
from settings import get_settings
from shared.cache import get_redis
from shared.lookups import is_servable

SLOT_KEYS: frozenset[str] = frozenset(
    {
        "directory_browse",
        # M2 milk surfaces. Naming contract {vertical}_{placement}: a future
        # theorganic_global_header is one more line here, pure config.
        "milk_global_header",
        "milk_home_hero",
        "milk_category_banner",
        "milk_search_inline",
        "milk_profile_footer",
    }
)
MAX_TARGET_URL = 2048
MAX_SERVE_COUNT = 5  # M2 carousel ceiling
LOCALES = ("en", "ta", "hi")

_PINCODE_RE = re.compile(r"^\d{6}$")
_CATEGORY_RE = re.compile(r"^[a-z0-9-]{1,40}$")
_GEO_RUNGS = ("state", "district", "pincodes")


def validate_target_url(url: str) -> None:
    """Ad-as-XSS gate: http/https absolute URLs only (no javascript:, data:,
    scheme-relative or fragment tricks). Called at creative create AND at
    serve time (defense in depth - a bad row must still never reach a page)."""
    if len(url) > MAX_TARGET_URL:
        raise ValueError("target_url too long")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("target_url must be an absolute http(s) URL")


class GeoTargetIn(BaseModel):
    """{} means serve everywhere; unknown keys are rejected outright."""

    model_config = ConfigDict(extra="forbid")

    state: int | None = None
    district: int | None = None
    pincodes: list[str] | None = Field(default=None, max_length=50)
    # M2: category-targetable inventory. Shape-validated only; matched at
    # serve time by exact string against the M1 schema `category` values, so
    # a new schema category is targetable with zero code changes here.
    categories: list[str] | None = Field(default=None, max_length=20)

    @field_validator("pincodes")
    @classmethod
    def _pincode_shape(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        bad = [p for p in value if not _PINCODE_RE.fullmatch(p)]
        if bad:
            raise ValueError(f"invalid pincodes: {bad!r}")
        return value

    @field_validator("categories")
    @classmethod
    def _category_shape(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        bad = [c for c in value if not _CATEGORY_RE.fullmatch(c)]
        if bad:
            raise ValueError(f"invalid categories: {bad!r}")
        return value


def viewer_hash(ip: str, user_agent: str, *, now: datetime) -> str:
    """Daily-rotating pseudonym: same viewer collapses within a UTC day (for
    freq-cap + dedupe) but is unlinkable across days (privacy: no durable
    tracking identifier, DPDP-minimal)."""
    secret = get_settings().ads_beacon_secret
    raw = f"{secret}:{now:%Y%m%d}:{ip}:{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()


def geo_matches(
    geo_target: dict[str, Any],
    *,
    pincode: str | None,
    district_lgd: int | None,
    state_lgd: int | None,
) -> bool:
    """No geo rung declared = everywhere (the M2 `categories` key is NOT a
    geo rung). Otherwise ANY declared rung matching the resolved chain is a
    hit; nothing else matches (non-negotiable 2). An unknown viewer location
    (pincode=None) matches only geo-untargeted placements - fail closed."""
    if not any(geo_target.get(k) for k in _GEO_RUNGS):
        return True
    pincodes = geo_target.get("pincodes") or []
    if pincode is not None and pincode in pincodes:
        return True
    district = geo_target.get("district")
    if district is not None and district_lgd is not None and district == district_lgd:
        return True
    state = geo_target.get("state")
    return state is not None and state_lgd is not None and state == state_lgd


def category_matches(geo_target: dict[str, Any], category: str | None) -> bool:
    """M2: no categories declared = every context; declared = the serve
    request must carry one of them. Same fail-closed shape as geo."""
    wanted = geo_target.get("categories") or []
    if not wanted:
        return True
    return category is not None and category in wanted


async def eligible_placements(
    session: AsyncSession,
    *,
    slot_key: str,
    pincode: str | None,
    today: date,
    category: str | None = None,
) -> list[tuple[Placement, Creative]]:
    """Active placement + active in-flight campaign + latest APPROVED creative
    + geo match + category match (M2). Row volume per slot is tiny in v1 -
    geo filtering in Python keeps the JSONB semantics in one testable
    function. pincode=None (M2 global slots before any location is known)
    skips resolution entirely: only geo-untargeted placements can match."""
    district_lgd = None
    state_lgd = None
    if pincode is not None:
        from shared.geo.service import district_for_pincode

        district = await district_for_pincode(session, pincode)
        district_lgd = district.lgd_code if district else None
        if district is not None:
            from shared.geo.models import State

            state = await session.get(State, district.state_id)
            state_lgd = state.lgd_code if state else None

    rows = (
        await session.execute(
            select(Placement, Creative, Campaign.advertiser_business_id)
            .join(Campaign, Campaign.id == Placement.campaign_id)
            .join(Creative, Creative.campaign_id == Campaign.id)
            .where(
                Placement.slot_key == slot_key,
                Placement.status == "active",
                Campaign.status == "active",
                Campaign.flight_start <= today,
                Campaign.flight_end >= today,
                Creative.moderation_status == "approved",
            )
            .order_by(Creative.id.desc())
        )
    ).all()
    # M1.5.E serve-time enforcement check (the M3 seam, live now): a
    # suspended/disabled advertiser's ads never serve, whatever the campaign
    # row says. One lookup per distinct advertiser; fail closed on unknowns.
    servable = {
        business_id: await is_servable(session, business_id)
        for business_id in {advertiser_id for _, _, advertiser_id in rows}
    }
    seen: set[uuid.UUID] = set()
    out: list[tuple[Placement, Creative]] = []
    for placement, creative, advertiser_id in rows:
        if placement.id in seen:  # newest approved creative per placement
            continue
        if not servable.get(advertiser_id, False):
            continue
        if geo_matches(
            placement.geo_target, pincode=pincode, district_lgd=district_lgd, state_lgd=state_lgd
        ) and category_matches(placement.geo_target, category):
            seen.add(placement.id)
            out.append((placement, creative))
    return out


async def pause_active_campaigns(session: AsyncSession, business_id: uuid.UUID) -> list[str]:
    """M1.5.B disable hook (registered as shared.lookups' campaign pauser):
    pause the advertiser's ACTIVE campaigns in the caller's transaction and
    return their ids - the audit row's manual-handling flag (no refund logic
    v1). Draft/paused/archived rows are untouched; nothing un-pauses here."""
    campaigns = (
        await session.scalars(
            select(Campaign).where(
                Campaign.advertiser_business_id == business_id,
                Campaign.status == "active",
            )
        )
    ).all()
    for campaign in campaigns:
        campaign.status = "paused"
    await session.flush()
    return [str(campaign.id) for campaign in campaigns]


def pick_weighted(
    candidates: list[tuple[Placement, Creative]], rand: random.Random
) -> tuple[Placement, Creative]:
    weights = [p.weight for p, _ in candidates]
    return rand.choices(candidates, weights=weights, k=1)[0]


def _seconds_to_utc_midnight(now: datetime) -> int:
    midnight = datetime.combine(now.date() + timedelta(days=1), time(0), tzinfo=UTC)
    return max(int((midnight - now).total_seconds()), 60)


def _freq_key(viewer: str, placement_id: uuid.UUID, now: datetime) -> str:
    return f"ads:freq:{viewer}:{placement_id}:{now:%Y%m%d}"


async def under_freq_cap(viewer: str, placement_id: uuid.UUID, *, cap: int, now: datetime) -> bool:
    count = await get_redis().get(_freq_key(viewer, placement_id, now))
    return int(count or 0) < cap


async def record_serve(viewer: str, placement_id: uuid.UUID, *, now: datetime) -> None:
    key = _freq_key(viewer, placement_id, now)
    redis = get_redis()
    await redis.incr(key)
    await redis.expire(key, _seconds_to_utc_midnight(now))
