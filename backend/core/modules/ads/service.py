"""Ads service (D21): validation + (Task 8) serving eligibility."""

import hashlib
import random
import re
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, NamedTuple, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign, Creative, DeliveryDecision, Placement
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
        # M3.B: sponsored listings injected into result lists at the render
        # layer (positions 1+6, max 2/page - enforced client-side; the engine
        # just serves count<=MAX_SERVE_COUNT like any slot).
        "milk_sponsored_listing",
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
    # M5: tier targeting ("all T3 towns in TN") - a FILTER alongside
    # `categories`, never a geo rung (geo_match_rung stays untouched).
    tiers: list[Annotated[int, Field(ge=1, le=5)]] | None = Field(default=None, max_length=5)

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


class Candidate(NamedTuple):
    """One servable (placement, newest-approved-creative) pair. `rung` is the
    geo rung that matched - the M3 blend discriminator: "global" for
    untargeted placements, else the most specific matched rung. Feeds both
    the local-boost rotation and the why-served log."""

    placement: Placement
    creative: Creative
    campaign: Campaign
    rung: str


def geo_match_rung(
    geo_target: dict[str, Any],
    *,
    pincode: str | None,
    district_lgd: int | None,
    state_lgd: int | None,
) -> str | None:
    """No geo rung declared = everywhere -> "global" (the M2 `categories` key
    is NOT a geo rung). Otherwise the most specific declared rung matching
    the resolved chain; None if nothing matches (non-negotiable 2). An
    unknown viewer location (pincode=None) matches only geo-untargeted
    placements - fail closed."""
    if not any(geo_target.get(k) for k in _GEO_RUNGS):
        return "global"
    pincodes = geo_target.get("pincodes") or []
    if pincode is not None and pincode in pincodes:
        return "pincode"
    district = geo_target.get("district")
    if district is not None and district_lgd is not None and district == district_lgd:
        return "district"
    state = geo_target.get("state")
    if state is not None and state_lgd is not None and state == state_lgd:
        return "state"
    return None


def geo_matches(
    geo_target: dict[str, Any],
    *,
    pincode: str | None,
    district_lgd: int | None,
    state_lgd: int | None,
) -> bool:
    return (
        geo_match_rung(geo_target, pincode=pincode, district_lgd=district_lgd, state_lgd=state_lgd)
        is not None
    )


def category_matches(geo_target: dict[str, Any], category: str | None) -> bool:
    """M2: no categories declared = every context; declared = the serve
    request must carry one of them. Same fail-closed shape as geo."""
    wanted = geo_target.get("categories") or []
    if not wanted:
        return True
    return category is not None and category in wanted


def tier_matches(geo_target: dict[str, Any], tier: int | None) -> bool:
    """M5 tier targeting - a filter like categories, not a geo rung (fail
    closed): no `tiers` declared = every context; declared = the resolved
    viewer tier (shared.geo.service.get_tier, None when no pincode) must be
    one of them."""
    wanted = geo_target.get("tiers")
    if not wanted:
        return True
    return tier is not None and tier in {int(t) for t in wanted}


async def eligible_placements(
    session: AsyncSession,
    *,
    slot_key: str,
    pincode: str | None,
    today: date,
    category: str | None = None,
    tier: int | None = None,
) -> list[Candidate]:
    """Active placement + active in-flight in-budget campaign + latest
    APPROVED creative + geo match + category match (M2) + tier match (M5).
    Row volume per slot is tiny in v1 - geo filtering in Python keeps the
    JSONB semantics in one testable function. pincode=None (M2 global slots
    before any location is known) skips resolution entirely: only
    geo-untargeted placements can match; tier is also None then, so a
    tier-targeted placement never matches either (fail closed)."""
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
            select(Placement, Creative, Campaign)
            .join(Campaign, Campaign.id == Placement.campaign_id)
            .join(Creative, Creative.campaign_id == Campaign.id)
            .where(
                Placement.slot_key == slot_key,
                Placement.status == "active",
                Campaign.status == "active",
                Campaign.flight_start <= today,
                Campaign.flight_end >= today,
                # M3: in-budget (NULL total = unlimited); the serve-time
                # consume_budget UPDATE closes the concurrent-race window.
                or_(
                    Campaign.budget_serves_total.is_(None),
                    Campaign.budget_serves_used < Campaign.budget_serves_total,
                ),
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
        for business_id in {campaign.advertiser_business_id for _, _, campaign in rows}
    }
    seen: set[uuid.UUID] = set()
    out: list[Candidate] = []
    for placement, creative, campaign in rows:
        if placement.id in seen:  # newest approved creative per placement
            continue
        if not servable.get(campaign.advertiser_business_id, False):
            continue
        rung = geo_match_rung(
            placement.geo_target, pincode=pincode, district_lgd=district_lgd, state_lgd=state_lgd
        )
        if rung is None or not category_matches(placement.geo_target, category):
            continue
        if not tier_matches(placement.geo_target, tier):
            continue
        seen.add(placement.id)
        out.append(Candidate(placement, creative, campaign, rung))
    return out


async def consume_budget(session: AsyncSession, campaign: Campaign) -> bool:
    """Atomic serve-credit decrement (M3 threat: budget race on concurrent
    serves). Unlimited campaigns (budget_serves_total IS NULL) never touch
    the row - no hot-row contention on house ads. The conditional UPDATE is
    the atomicity: a concurrent loser blocks on the row lock, re-evaluates
    the WHERE against the committed value, and matches zero rows once the
    last credit is gone - it must then NOT serve. The caller owns the
    commit."""
    if campaign.budget_serves_total is None:
        return True
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(Campaign)
            .where(
                Campaign.id == campaign.id,
                Campaign.budget_serves_used < Campaign.budget_serves_total,
            )
            .values(budget_serves_used=Campaign.budget_serves_used + 1)
        ),
    )
    return result.rowcount == 1


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
    candidates: list[Candidate], rand: random.Random, *, local_boost: float = 1.0
) -> Candidate:
    """Weighted rotation with the M3 blend boost: local-targeted candidates
    (any matched geo rung) count local_boost x their placement weight so
    village advertisers aren't drowned by national ALL-pincode brands."""
    weights = [
        c.placement.weight * (local_boost if c.rung != "global" else 1.0) for c in candidates
    ]
    return rand.choices(candidates, weights=weights, k=1)[0]


def _seconds_to_utc_midnight(now: datetime) -> int:
    midnight = datetime.combine(now.date() + timedelta(days=1), time(0), tzinfo=UTC)
    return max(int((midnight - now).total_seconds()), 60)


def _freq_key(viewer: str, creative_id: uuid.UUID, now: datetime) -> str:
    # M3.A: capped per user-session per CREATIVE. The daily-rotating
    # viewer_hash IS the session pseudonym; keys expire at UTC midnight with it.
    return f"ads:freq:{viewer}:{creative_id}:{now:%Y%m%d}"


async def under_freq_cap(viewer: str, creative_id: uuid.UUID, *, cap: int, now: datetime) -> bool:
    count = await get_redis().get(_freq_key(viewer, creative_id, now))
    return int(count or 0) < cap


async def record_serve(viewer: str, creative_id: uuid.UUID, *, now: datetime) -> None:
    key = _freq_key(viewer, creative_id, now)
    redis = get_redis()
    await redis.incr(key)
    await redis.expire(key, _seconds_to_utc_midnight(now))


def log_delivery(
    session: AsyncSession,
    *,
    candidate: Candidate,
    slot_key: str,
    pincode: str | None,
    category: str | None,
    viewer: str,
    now: datetime,
    rand: random.Random,
    tier: int | None = None,
) -> bool:
    """M3.E: append-only, SAMPLED why-served row for advertiser analytics
    (M5) and dispute resolution. Returns True when a row was staged - the
    caller owns the commit. pincode/category are serve context (fine to
    keep); viewer is the daily-rotating hash - never any other user
    identifier (threat: delivery-log PII). tier is the M4 pincode tier
    resolved by the caller via shared.geo.service.get_tier (None when the
    request carried no pincode)."""
    rate = get_settings().ads_delivery_log_sample
    if rate <= 0 or rand.random() >= rate:
        return False
    session.add(
        DeliveryDecision(
            campaign_id=candidate.campaign.id,
            placement_id=candidate.placement.id,
            creative_id=candidate.creative.id,
            slot_key=slot_key,
            pincode=pincode,
            category=category,
            why_served="global" if candidate.rung == "global" else f"local_{candidate.rung}",
            viewer_hash=viewer,
            occurred_at=now,
            tier=tier,
        )
    )
    return True
