"""House-ad fill (M2.E): first-party creatives on every milk ad slot so
surfaces are never empty. This is legitimate PRODUCTION content (unlike the
e2e fixtures) - deliberately no refuse_in_prod; see test_dev_only_guard.py.
Idempotent: keyed on campaign name; re-runs reconcile status/flight_end.

Campaign-per-message on purpose: eligible_placements() serves the newest
approved creative per placement, and a placement belongs to one campaign -
distinct messages must be distinct campaigns to rotate in the carousel.

Run:
    cd backend/core
    .venv/Scripts/python.exe scripts/seed_house_ads.py \
        [--base-url http://localhost:3000] \
        [--console-url http://localhost:3002/business/listings] \
        [--enable-flag] [--enable-billing-flag] [--reset-caps] \
        [--with-sponsored-listing]
"""

import argparse
import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign, Creative, Placement
from modules.directory import service as directory_service
from modules.directory.models import Business
from settings import get_settings
from shared.cache import get_redis
from shared.db import get_sessionmaker
from shared.flags import FeatureFlag, reset_flag_cache

_HOUSE_BUSINESS = "Milk.in House"
_PINCODE = "641001"
_FLIGHT_DAYS = 3650  # effectively evergreen; re-runs extend

MILK_SLOTS = (
    "milk_global_header",
    "milk_home_hero",
    "milk_category_banner",
    "milk_search_inline",
    "milk_profile_footer",
)


def _messages(base_url: str, console_url: str) -> list[tuple[str, dict[str, dict[str, str]], str]]:
    return [
        (
            "post-need",
            {
                "en": {
                    "title": "Post your need",
                    "body": "Tell vendors what you need - they reply to you.",
                },
                "ta": {
                    "title": "உங்கள் தேவையை பதிவிடுங்கள்",
                    "body": "விற்பனையாளர்கள் உங்களை தொடர்பு கொள்வார்கள்.",
                },
                "hi": {
                    "title": "अपनी ज़रूरत पोस्ट करें",
                    "body": "विक्रेता आपको जवाब देंगे।",
                },
            },
            f"{base_url}/post-need",
        ),
        (
            "list-business",
            {
                "en": {
                    "title": "List your business",
                    "body": "Reach milk buyers near you - free listing.",
                },
                "ta": {
                    "title": "உங்கள் வணிகத்தைப் பதிவு செய்யுங்கள்",
                    "body": "அருகிலுள்ள வாடிக்கையாளர்களை அடையுங்கள்.",
                },
                "hi": {
                    "title": "अपना व्यवसाय जोड़ें",
                    "body": "आस-पास के ग्राहकों तक पहुंचें।",
                },
            },
            console_url,
        ),
    ]


async def _ensure_house_business(session: AsyncSession) -> uuid.UUID:
    """Serve-time is_servable() is fail-closed, so the house advertiser must
    be a real, active directory business. owner_user_id is NOT an FK into
    identity (module-independence contract), so a bare uuid4 owner is fine -
    same shape the ads serve tests use."""
    existing = await session.scalar(select(Business).where(Business.name == _HOUSE_BUSINESS))
    if existing is not None:
        return existing.id
    business = await directory_service.create_business(
        session,
        owner_user_id=uuid.uuid4(),
        name=_HOUSE_BUSINESS,
        type_="shop",
        primary_pincode=_PINCODE,
    )
    await session.commit()
    print(f"seed_house_ads: created house business {business.slug}")  # noqa: T201
    return business.id


async def _ensure_house_ad(
    session: AsyncSession,
    *,
    advertiser_id: uuid.UUID,
    slot_key: str,
    tag: str,
    copy: dict[str, dict[str, str]],
    target_url: str,
) -> None:
    name = f"House · {slot_key} · {tag}"
    today = date.today()
    campaign = await session.scalar(select(Campaign).where(Campaign.name == name))
    if campaign is not None:  # reconcile, don't duplicate
        campaign.status = "active"
        campaign.flight_end = today + timedelta(days=_FLIGHT_DAYS)
        await session.commit()
        return
    campaign = Campaign(
        advertiser_business_id=advertiser_id,
        name=name,
        status="active",
        flight_start=today - timedelta(days=1),
        flight_end=today + timedelta(days=_FLIGHT_DAYS),
    )
    session.add(campaign)
    await session.flush()
    session.add(
        Creative(
            campaign_id=campaign.id,
            media_keys=[],  # copy-only house card; AdSlot renders the text variant
            copy=copy,
            target_url=target_url,
            moderation_status="approved",  # first-party content, pre-approved
        )
    )
    session.add(Placement(campaign_id=campaign.id, slot_key=slot_key, geo_target={}, weight=1))
    await session.commit()
    print(f"seed_house_ads: created {name}")  # noqa: T201


async def _enable_flag(session: AsyncSession) -> None:
    if get_settings().app_env == "prod":
        raise SystemExit("--enable-flag refused in prod: flip ads_enabled via /admin/ops/flags")
    flag = await session.get(FeatureFlag, "ads_enabled")
    if flag is None:
        raise RuntimeError("ads_enabled flag missing - run `alembic upgrade head`")
    if not flag.enabled:
        flag.enabled = True
        await session.commit()
        reset_flag_cache()
        print("seed_house_ads: ads_enabled -> true")  # noqa: T201


async def _enable_billing_flag(session: AsyncSession) -> None:
    """M5 Task 17 (e2e NN1): flips `billing_enabled` the same way
    `--enable-flag` flips `ads_enabled` above - identical refuse-in-prod
    guard, identical idempotent no-op-if-already-on shape. Lets
    e2e/advertiser-selfserve.spec.ts drive a real create -> pay(test) ->
    approve -> targeted-serve walk against the Razorpay test stub with zero
    real Razorpay credentials. Deliberately a SEPARATE flag from
    `--enable-flag` (ads_enabled): a caller that only wants house-ad fill
    must not accidentally light up the money path too."""
    if get_settings().app_env == "prod":
        raise SystemExit(
            "--enable-billing-flag refused in prod: flip billing_enabled via /admin/ops/flags"
        )
    flag = await session.get(FeatureFlag, "billing_enabled")
    if flag is None:
        raise RuntimeError("billing_enabled flag missing - run `alembic upgrade head`")
    if not flag.enabled:
        flag.enabled = True
        await session.commit()
        reset_flag_cache()
        print("seed_house_ads: billing_enabled -> true")  # noqa: T201


async def _reset_caps() -> None:
    """e2e/dev determinism: every request from one machine shares a viewer
    hash (same IP+UA, daily window), so the 3/day serve cap exhausts the
    house placements after a few page loads and every later assertion sees
    the fallback instead of a served ad. Never a prod operation."""
    if get_settings().app_env == "prod":
        raise SystemExit("--reset-caps refused in prod: serve caps are a fraud control")
    redis = get_redis()
    deleted = 0
    for pattern in ("ads:freq:*", "ads:dedupe:*"):
        async for key in redis.scan_iter(match=pattern):
            await redis.delete(key)
            deleted += 1
    print(f"seed_house_ads: cleared {deleted} serve-cap/dedupe keys")  # noqa: T201


async def run(
    base_url: str,
    console_url: str,
    enable_flag: bool,
    reset_caps: bool,
    with_sponsored_listing: bool = False,
    enable_billing_flag: bool = False,
) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        advertiser_id = await _ensure_house_business(session)
        for slot_key in MILK_SLOTS:
            for tag, copy, target_url in _messages(base_url, console_url):
                await _ensure_house_ad(
                    session,
                    advertiser_id=advertiser_id,
                    slot_key=slot_key,
                    tag=tag,
                    copy=copy,
                    target_url=target_url,
                )
        if with_sponsored_listing:
            # M3.B e2e determinism: a house card at position 1 of every list
            # is not a prod default, so this slot only seeds behind the flag.
            await _ensure_house_ad(
                session,
                advertiser_id=advertiser_id,
                slot_key="milk_sponsored_listing",
                tag="discover",
                copy={
                    "en": {"title": "Milk.in Partner Dairy", "body": "Fresh local milk, delivered"},
                    "ta": {"title": "Milk.in கூட்டாளர் பால் பண்ணை", "body": "புதிய உள்ளூர் பால்"},
                    "hi": {"title": "Milk.in पार्टनर डेयरी", "body": "ताज़ा स्थानीय दूध"},
                },
                target_url=f"{base_url}/coimbatore/641001",
            )
        if enable_flag:
            await _enable_flag(session)
        if enable_billing_flag:
            await _enable_billing_flag(session)
    if reset_caps:
        await _reset_caps()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--console-url", default="http://localhost:3002/business/listings")
    parser.add_argument("--enable-flag", action="store_true")
    parser.add_argument("--reset-caps", action="store_true")
    parser.add_argument("--with-sponsored-listing", action="store_true")
    parser.add_argument("--enable-billing-flag", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        run(
            args.base_url,
            args.console_url,
            args.enable_flag,
            args.reset_caps,
            args.with_sponsored_listing,
            args.enable_billing_flag,
        )
    )
