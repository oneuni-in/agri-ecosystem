"""U1 demo depth: make the milk home look like a live marketplace.

The database already has ~100 businesses covering the launch pincode, but the
home rendered thin because three signals were almost absent:

  * verification - exactly ONE covering business was `verified`, so the
    "Verified vendor" badge, the verified-vendors stat and the M3.C
    Recommended rail (which needs +3.0 from verification to clear MIN_SCORE)
    had nothing to show;
  * reviews - only two businesses had any, so vendor cards carried no rating
    and the reviews strip showed the same vendor twice;
  * advertisers - every creative belonged to the house advertiser, so the ad
    surfaces never demonstrated a real paid placement.

This script fills those three gaps and nothing else. It creates no businesses:
it decorates the ones the real vendor import already produced, which keeps the
demo honest (the names, coverage and products are the imported catalogue, not
invented rows).

Idempotent: verification is reconciled, reviews are keyed on (author, target)
via the D18 one-per-user constraint, and campaigns are keyed on name.

Run (after seed_e2e_milk.py / import_vendor_seed.py):
    cd backend/core
    .venv/Scripts/python.exe scripts/seed_u1_demo.py [--pincode 641001]
"""

import argparse
import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign, Creative, Placement
from modules.directory import reviews_service
from modules.directory import service as directory_service
from modules.directory.models import Business
from modules.identity import service as identity_service
from shared.db import get_sessionmaker
from shared.dev_only import refuse_in_prod

_DEFAULT_PINCODE = "641001"
# How many covering businesses to verify / review. Deliberately a MINORITY of
# the ~100 covering rows: a directory where everything is verified teaches the
# reader that the badge is meaningless.
_VERIFY_COUNT = 14
_REVIEW_BUSINESSES = 12
_ADVERTISER = "Kovai Dairy Collective"

# Review authors. Real identity users (reviews.author_user_id is a user id and
# the D18 unique constraint is per author+target), so one author can review
# many businesses but never the same one twice.
_AUTHOR_PHONES = [f"+9190000001{n:02d}" for n in range(10)]

# (rating, body). Mixed EN/TA on purpose - the reviews strip renders the
# reader's locale when the author wrote in it and falls back to what they
# actually wrote, so a Tamil review must survive on /en.
_REVIEW_TEXTS: list[tuple[int, dict[str, str]]] = [
    (5, {"en": "Fresh cow milk at the gate every morning. Never missed a day."}),
    (5, {"ta": "நல்ல தரமான பால். தினமும் காலை சரியான நேரத்தில் வருகிறது."}),
    (4, {"en": "Good milk and fair price. Delivery is sometimes ten minutes late."}),
    (5, {"en": "Switched from a packet brand to this farm. The difference is obvious."}),
    (5, {"ta": "விலை நியாயமாக இருக்கிறது. குடும்பத்திற்கு போதுமான அளவு கிடைக்கிறது."}),
    (4, {"en": "Buffalo milk is thick and clean. Bottles are collected back."}),
    (5, {"en": "Called once and they started next morning. No advance, no deposit."}),
    (4, {"ta": "பண்ணையில் இருந்து நேரடியாக வருகிறது. நம்பிக்கையாக இருக்கு."}),
    (5, {"en": "A2 milk was hard to find nearby until I searched here."}),
    (4, {"en": "Curd and ghee are also good. Ordering on WhatsApp is easy."}),
]

# Sample ADS from a real (non-house) advertiser: geo-targeted to the launch
# pincode, with a serve budget, so the surfaces demonstrate a paid placement
# rather than only first-party house fill.
_ADS: list[tuple[str, str, dict[str, dict[str, str]], str]] = [
    (
        "hero",
        "milk_home_hero_xl",
        {
            "en": {
                "title": "Farm-fresh A2 milk, delivered by 6 AM",
                "body": "Kovai Dairy Collective - 40 farmer families, one doorstep.",
            },
            "ta": {
                "title": "பண்ணை புதிய A2 பால், காலை 6 மணிக்குள்",
                "body": "கோவை பால் கூட்டமைப்பு - 40 விவசாய குடும்பங்கள்.",
            },
            "hi": {
                "title": "ताज़ा A2 दूध, सुबह 6 बजे तक",
                "body": "कोवई डेयरी कलेक्टिव - 40 किसान परिवार।",
            },
        },
        "/coimbatore/641001",
    ),
    (
        "banner",
        "milk_category_banner",
        {
            "en": {
                "title": "Ghee pressed the old way",
                "body": "Wood-churned, this week only.",
            },
            "ta": {"title": "பாரம்பரிய முறையில் நெய்", "body": "இந்த வாரம் மட்டும்."},
            "hi": {"title": "पारंपरिक तरीके से घी", "body": "सिर्फ़ इस हफ़्ते।"},
        },
        "/p/ghee",
    ),
    (
        "listing",
        "milk_sponsored_listing",
        {
            "en": {
                "title": "Kovai Dairy Collective",
                "body": "Daily cow, buffalo and A2 - covers 641001-641004.",
            },
            "ta": {
                "title": "கோவை பால் கூட்டமைப்பு",
                "body": "பசு, எருமை, A2 - 641001-641004 பகுதிகளில்.",
            },
            "hi": {
                "title": "कोवई डेयरी कलेक्टिव",
                "body": "गाय, भैंस और A2 - 641001-641004 में।",
            },
        },
        "/coimbatore/641001",
    ),
]

# Covering businesses that actually surface on the home: active, with at least
# one approved+active milk product. Same predicate milk_home() uses, so this
# never decorates a business the page will not show.
_COVERING_SQL = text(
    """
    SELECT DISTINCT b.id
    FROM directory.business_coverage c
    JOIN directory.businesses b
      ON b.id = c.business_id AND b.status = 'active' AND b.deleted_at IS NULL
    WHERE c.pincode = :pincode
      AND EXISTS (
        SELECT 1 FROM directory.products pr
        WHERE pr.business_id = b.id AND pr.vertical_slug = 'milk'
          AND pr.moderation_status = 'approved' AND pr.status = 'active'
          AND pr.deleted_at IS NULL
      )
    ORDER BY b.id
    """
)


async def _covering(session: AsyncSession, pincode: str) -> list[uuid.UUID]:
    rows = await session.execute(_COVERING_SQL, {"pincode": pincode})
    return [r[0] for r in rows]


async def _verify(session: AsyncSession, ids: list[uuid.UUID]) -> int:
    """Mark a minority of covering businesses `verified` - the same column the
    D16 claim-decision route sets. Reconciles rather than duplicating."""
    changed = 0
    for business_id in ids[:_VERIFY_COUNT]:
        business = await session.get(Business, business_id)
        if business is None or business.verification_status == "verified":
            continue
        business.verification_status = "verified"
        changed += 1
    if changed:
        await session.commit()
    return changed


async def _authors(session: AsyncSession) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for phone in _AUTHOR_PHONES:
        user = await identity_service.get_by_phone(session, phone)
        if user is None:
            user = await identity_service.create_user(session, phone)
            await session.commit()
        out.append(user.id)
    return out


async def _review(session: AsyncSession, ids: list[uuid.UUID], authors: list[uuid.UUID]) -> int:
    """Spread approved reviews across businesses.

    `reviews_service.moderate()` deliberately does NOT touch the cached
    aggregate - the admin route calls `recompute_aggregate()` after it. This
    script is standing in for that route, so it must do the same: without the
    recompute the rows exist but every card reads rating 0, which is exactly
    what happened on the first run here.

    The recompute runs for every business touched, not only ones that gained
    a review, so a re-run repairs aggregates left behind by an earlier pass.
    """
    added = 0
    for index, business_id in enumerate(ids[:_REVIEW_BUSINESSES]):
        # 2-3 reviews each, from different authors, so counts vary per card.
        for offset in range(2 + (index % 2)):
            author = authors[(index * 3 + offset) % len(authors)]
            held = await session.scalar(
                select(func.count())
                .select_from(reviews_service.Review)
                .where(
                    reviews_service.Review.author_user_id == author,
                    reviews_service.Review.target_type == "business",
                    reviews_service.Review.target_id == business_id,
                )
            )
            if held:
                continue
            rating, body = _REVIEW_TEXTS[(index * 3 + offset) % len(_REVIEW_TEXTS)]
            review = await reviews_service.create_review(
                session,
                author_user_id=author,
                target_type="business",
                target_id=business_id,
                rating=rating,
                body=body,
            )
            await session.commit()
            await reviews_service.moderate(session, review_id=review.id, approve=True)
            await session.commit()
            added += 1
        # What the admin route does after every decision. Skipping it is why
        # 41 approved reviews once produced only 2 rating aggregates.
        await reviews_service.recompute_aggregate(
            session, target_type="business", target_id=business_id
        )
        await session.commit()
    return added


async def _ads(session: AsyncSession, pincode: str) -> int:
    """A real advertiser with geo-targeted, budgeted, approved creatives.

    Serve-time `is_servable()` is fail-closed, so the advertiser must be a real
    active directory business - the same requirement seed_house_ads.py
    documents for the house advertiser.
    """
    advertiser = await session.scalar(select(Business).where(Business.name == _ADVERTISER))
    if advertiser is None:
        advertiser = await directory_service.create_business(
            session,
            owner_user_id=uuid.uuid4(),  # not an FK into identity (module independence)
            name=_ADVERTISER,
            type_="shop",
            primary_pincode=pincode,
        )
        await session.commit()

    today = date.today()
    added = 0
    for tag, slot_key, copy, path in _ADS:
        name = f"Demo - {_ADVERTISER} - {tag}"
        if await session.scalar(select(Campaign).where(Campaign.name == name)):
            continue
        campaign = Campaign(
            advertiser_business_id=advertiser.id,
            name=name,
            status="active",
            flight_start=today - timedelta(days=1),
            flight_end=today + timedelta(days=365),
            budget_display="Demo budget",
            budget_serves_total=100_000,
        )
        session.add(campaign)
        await session.flush()
        session.add(
            Creative(
                campaign_id=campaign.id,
                media_keys=[],  # copy-only: renders the text variant, which reads
                # correctly at every slot size (see seed_sample_media._SLOT_SIZES)
                copy=copy,
                target_url=f"http://localhost:3000{path}",
                moderation_status="approved",
            )
        )
        session.add(
            Placement(
                campaign_id=campaign.id,
                slot_key=slot_key,
                geo_target={"pincodes": [pincode]},
                weight=1,
            )
        )
        await session.commit()
        added += 1
    return added


async def run(pincode: str) -> None:
    refuse_in_prod("seed_u1_demo.py")
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        ids = await _covering(session, pincode)
        if not ids:
            print(f"seed_u1_demo: no covering businesses at {pincode} - run the seeds first")  # noqa: T201
            return
        verified = await _verify(session, ids)
        authors = await _authors(session)
        reviews = await _review(session, ids, authors)
        ads = await _ads(session, pincode)
    print(  # noqa: T201
        f"seed_u1_demo: {len(ids)} covering at {pincode} -> "
        f"+{verified} verified, +{reviews} approved reviews, +{ads} advertiser campaigns"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pincode", default=_DEFAULT_PINCODE)
    asyncio.run(run(parser.parse_args().pincode))
