"""Sample media seed (manual-QA support): generate placeholder JPEGs and
attach them to (a) house-ad creatives and (b) milk products that have no
images yet, so ad surfaces and product cards render real pictures during
hand testing instead of text-only variants.

Every byte goes through shared.media.reencode_image (the sanctioned image
pipeline - EXIF stripped by construction) and lands in the MinIO bucket via
shared.storage.put_object, exactly like a real upload. Idempotent:
deterministic object keys, and rows that already carry media are skipped.

Run:
    cd backend/core
    .venv/Scripts/python.exe scripts/seed_sample_media.py
"""

import argparse
import asyncio
import io

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign, Creative, Placement
from modules.directory.catalog_models import Product
from modules.directory.models import Business
from shared import media, storage
from shared.db import get_sessionmaker

_HOUSE_BUSINESS = "Milk.in House"
# BOTH prefixes live under "products/": ensure_prefix_public_read() REPLACES the
# bucket policy wholesale, so a second prefix grant would clobber the first
# (catalog's own products/ grant). One public prefix, zero clobbering.
_AD_PREFIX = "products/sample-ads/"
_LEGACY_AD_PREFIX = "ads/sample/"  # first seed run used this; migrated below
_PRODUCT_PREFIX = "products/sample/"
_MAX_PRODUCTS = 80
_DEFAULT_AD_SIZE = (1200, 628)
# Creative size per slot. A slot is a SHAPE, not just a key: one 1200x628
# master cropped into a 64px banner box renders as an unreadable slice of
# giant text (AdImage is object-cover by contract). Each slot gets art at the
# ratio its reserved box actually uses.
_SLOT_SIZES = {
    "milk_home_hero_xl": (1600, 420),  # U1 §3 full-bleed home hero
    "milk_global_header": (1200, 160),  # thin page-head banner
    "milk_category_banner": (1200, 160),  # U1 §5d partner banner
    "milk_search_inline": (1200, 160),
    "milk_profile_footer": (1200, 200),
    "milk_sponsored_listing": (800, 600),  # M3.B injected card
}

# Milk-ish palette for generated cards (content, not UI - token rule doesn't apply)
_PALETTE = [
    ("#1b5e20", "#e8f5e9"),  # deep green on cream
    ("#4e342e", "#efebe9"),  # cocoa on milk
    ("#0d47a1", "#e3f2fd"),  # indigo on ice
    ("#b71c1c", "#fff8e1"),  # brick on butter
    ("#33691e", "#f9fbe7"),  # olive on whey
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def _make_card(lines: list[str], *, size: tuple[int, int], colors: tuple[str, str]) -> bytes:
    """A simple flat placeholder: colored panel, bold text, corner accent."""
    fg, bg = colors
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    w, h = size
    draw.rectangle([0, h - h // 8, w, h], fill=fg)  # footer bar
    draw.ellipse([w - w // 5, -w // 10, w + w // 10, w // 5], fill=fg)  # corner blob
    y = h // 5
    for index, line in enumerate(lines[:3]):
        font = _font(max(h // 8 - index * 10, 24))
        draw.text((w // 12, y), line, fill=fg if index == 0 else "#37474f", font=font)
        y += h // 5
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    jpeg, _ = media.reencode_image(buf.getvalue())  # THE shared pipeline
    return jpeg


async def _seed_creative_media(session: AsyncSession, reimage: bool = False) -> int:
    house = await session.scalar(select(Business).where(Business.name == _HOUSE_BUSINESS))
    if house is None:
        print("seed_sample_media: no house business - run seed_house_ads.py first")  # noqa: T201
        return 0
    rows = (
        await session.execute(
            select(Creative, Campaign.name, Placement.slot_key)
            .join(Campaign, Campaign.id == Creative.campaign_id)
            .join(Placement, Placement.campaign_id == Campaign.id)
            .where(Campaign.advertiser_business_id == house.id)
        )
    ).all()
    done = 0
    for index, (creative, campaign_name, slot_key) in enumerate(rows):
        if (
            not reimage
            and creative.media_keys
            and not creative.media_keys[0].startswith(_LEGACY_AD_PREFIX)
        ):
            continue  # already has media under the public prefix - idempotent skip
        copy_en = (creative.copy or {}).get("en", {})
        title = copy_en.get("title", campaign_name)
        body = copy_en.get("body", "")
        jpeg = _make_card(
            [title, body, "milk.in"],
            # U1 §3: the full-bleed home hero is a different shape from every
            # other slot - 1600x420 desktop. The page reserves 750/360 below
            # 768px and AdImage is object-cover, so one wide master crops
            # correctly on phones instead of letterboxing.
            size=_SLOT_SIZES.get(slot_key, _DEFAULT_AD_SIZE),
            colors=_PALETTE[index % len(_PALETTE)],
        )
        key = f"{_AD_PREFIX}{creative.id.hex}.jpg"
        await storage.put_object(key, jpeg, "image/jpeg")
        creative.media_keys = [key]  # new list - JSONB mutation isn't tracked
        done += 1
    return done


async def _seed_product_media(session: AsyncSession) -> int:
    products = (
        await session.scalars(
            select(Product)
            .where(
                Product.vertical_slug == "milk",
                Product.moderation_status == "approved",
                Product.status == "active",
                Product.media_keys == [],
            )
            .order_by(Product.id)
            .limit(_MAX_PRODUCTS)
        )
    ).all()
    done = 0
    for index, product in enumerate(products):
        category = product.specs.get("category") or product.specs.get("milk_type") or "dairy"
        price = product.price_display or ""
        jpeg = _make_card(
            [product.name, f"{category} {price}".strip()],
            size=(800, 600),
            colors=_PALETTE[index % len(_PALETTE)],
        )
        key = f"{_PRODUCT_PREFIX}{product.id.hex}.jpg"
        await storage.put_object(key, jpeg, "image/jpeg")
        product.media_keys = [key]
        done += 1
    return done


async def run(reimage: bool = False) -> None:
    # ONE grant only - see prefix comment above (policy calls replace, not merge)
    await storage.ensure_prefix_public_read("products/")
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        creatives = await _seed_creative_media(session, reimage)
        products = await _seed_product_media(session)
        await session.commit()
    print(f"seed_sample_media: {creatives} creatives + {products} products imaged")  # noqa: T201


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reimage",
        action="store_true",
        help="regenerate house-ad art at the current per-slot size (see _SLOT_SIZES)",
    )
    asyncio.run(run(parser.parse_args().reimage))
