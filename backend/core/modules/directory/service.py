"""Directory service layer (D15). Every write is owner-scoped through
owned_by(column="owner_user_id"); a non-owner gets BusinessNotFoundError,
which the router maps to the same 404 as a missing row (IDOR threat model).

Never log request bodies here - business contact PII flows through this module.
"""

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.models import Branch, Business, BusinessCategory, BusinessCoverage, Category
from shared.i18n import Translated
from shared.ownership import owned_by
from shared.pagination import DEFAULT_PAGE_SIZE, Page, paginate
from shared.slugs import change_slug

PINCODE_RE = re.compile(r"^\d{6}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_COVERAGE_PINCODES = 500
BUSINESS_PATH = "/directory/businesses/{slug}"

# The only owner-editable business columns. slug (rename endpoint),
# verification_status (D16 claim flow), subscription_tier (billing) and
# owner_user_id are one-way doors from this API's point of view.
MUTABLE_FIELDS = {"name", "type", "primary_pincode", "description", "delivery_windows"}


class BusinessNotFoundError(Exception):
    """No such business - or not yours. The router 404s both identically."""


class BusinessDisabledError(Exception):
    """M1.5.B hard-off: the owner console is locked while status='disabled'.
    Mapped app-wide to 403 'business_disabled' (main.create_app handler)."""


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or "business"


def _validate_pincode(pincode: str) -> None:
    if not PINCODE_RE.fullmatch(pincode):
        raise ValueError(f"not a 6-digit pincode: {pincode!r}")


async def _free_slug(session: AsyncSession, base: str) -> str:
    candidate, n = base, 1
    while (
        await session.scalar(
            select(Business.id)
            .where(Business.slug == candidate)
            # soft-deleted rows still hold their unique slug
            .execution_options(include_deleted=True)
        )
        is not None
    ):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


async def create_business(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    name: str,
    type_: str,
    primary_pincode: str,
    description: dict[str, str] | None = None,
) -> Business:
    _validate_pincode(primary_pincode)
    business = Business(
        owner_user_id=owner_user_id,
        name=name,
        slug=await _free_slug(session, _slugify(name)),
        type=type_,
        primary_pincode=primary_pincode,
        description=Translated.from_dict(description) if description else None,
    )
    session.add(business)
    await session.flush()
    await session.refresh(business)  # load server-side defaults (status, tier, ...)
    return business


async def get_owned_business(
    session: AsyncSession, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> Business:
    query = owned_by(
        select(Business).where(Business.id == business_id),
        owner_user_id,
        column="owner_user_id",
    )
    business = await session.scalar(query)
    if business is None:
        raise BusinessNotFoundError(str(business_id))
    if business.status == "disabled":
        # every owner-console read/write funnels through here: the lock is
        # one check, not N route guards. list_my_businesses stays unfiltered
        # so the console can render the locked card.
        raise BusinessDisabledError(str(business_id))
    return business


async def update_business(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    patch: dict[str, Any],
) -> Business:
    unknown = set(patch) - MUTABLE_FIELDS
    if unknown:
        raise ValueError(f"immutable or unknown fields: {sorted(unknown)}")
    business = await get_owned_business(session, owner_user_id, business_id)
    if "primary_pincode" in patch:
        _validate_pincode(patch["primary_pincode"])
    if "description" in patch:
        raw = patch.pop("description")
        business.description = Translated.from_dict(raw) if raw else None
    for field, value in patch.items():
        setattr(business, field, value)
    await session.flush()
    return business


async def select_tier(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    tier: str,
    now: datetime,
) -> Business:
    """Record premium INTENT (D26). Never writes subscription_tier - that
    column stays server-set (admin route / billing at launch): the
    fake-premium threat model's one-way door."""
    business = await get_owned_business(session, owner_user_id, business_id)
    business.premium_requested_at = now if tier == "premium" else None
    await session.flush()
    return business


async def list_my_businesses(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[Business]:
    return await paginate(
        session,
        owned_by(select(Business), owner_user_id, column="owner_user_id"),
        cursor=cursor,
        limit=limit,
    )


async def rename_business(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    new_slug: str,
) -> Business:
    if not SLUG_RE.fullmatch(new_slug):
        raise ValueError("slug must be lowercase letters/digits with single hyphens")
    business = await get_owned_business(session, owner_user_id, business_id)
    if new_slug == business.slug:
        return business
    taken = await session.scalar(
        select(Business.id)
        .where(Business.slug == new_slug)
        .execution_options(include_deleted=True)  # deleted rows still hold their slug
    )
    if taken is not None:
        raise ValueError(f"slug already taken: {new_slug}")
    change_slug(
        session,
        business,
        new_slug,
        old_path=BUSINESS_PATH.format(slug=business.slug),
        new_path=BUSINESS_PATH.format(slug=new_slug),
    )
    await session.flush()
    return business


BRANCH_MUTABLE_FIELDS = {
    "address",
    "state",
    "district",
    "pincode",
    "lat",
    "lng",
    "phone",
    "whatsapp",
    "hours",
}


async def add_branch(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    address: str,
    state: str,
    district: str,
    pincode: str,
    lat: Decimal | None = None,
    lng: Decimal | None = None,
    phone: str | None = None,
    whatsapp: str | None = None,
    hours: dict[str, Any] | None = None,
) -> Branch:
    _validate_pincode(pincode)
    await get_owned_business(session, owner_user_id, business_id)
    branch = Branch(
        business_id=business_id,
        address=address,
        state=state,
        district=district,
        pincode=pincode,
        lat=lat,
        lng=lng,
        phone=phone,
        whatsapp=whatsapp,
        hours=hours or {},
    )
    session.add(branch)
    await session.flush()
    return branch


async def update_branch(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    branch_id: uuid.UUID,
    patch: dict[str, Any],
) -> Branch:
    unknown = set(patch) - BRANCH_MUTABLE_FIELDS
    if unknown:
        raise ValueError(f"unknown branch fields: {sorted(unknown)}")
    branch = await session.scalar(select(Branch).where(Branch.id == branch_id))
    if branch is None:
        raise BusinessNotFoundError(str(branch_id))
    # parent-ownership gate: not the owner -> same 404 as a missing branch
    await get_owned_business(session, owner_user_id, branch.business_id)
    if "pincode" in patch:
        _validate_pincode(patch["pincode"])
    for field, value in patch.items():
        setattr(branch, field, value)
    await session.flush()
    return branch


async def set_coverage(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    pincodes: list[str],
) -> list[str]:
    wanted = sorted(set(pincodes))
    if len(wanted) > MAX_COVERAGE_PINCODES:
        raise ValueError(f"coverage capped at {MAX_COVERAGE_PINCODES} pincodes")
    bad = [p for p in wanted if not PINCODE_RE.fullmatch(p)]
    if bad:
        raise ValueError(f"not 6-digit pincodes: {bad[:5]}")
    await get_owned_business(session, owner_user_id, business_id)
    existing = set(
        (
            await session.scalars(
                select(BusinessCoverage.pincode).where(BusinessCoverage.business_id == business_id)
            )
        ).all()
    )
    stale = existing - set(wanted)
    if stale:
        await session.execute(
            delete(BusinessCoverage).where(
                BusinessCoverage.business_id == business_id,
                BusinessCoverage.pincode.in_(stale),
            )
        )
    for pincode in set(wanted) - existing:
        session.add(BusinessCoverage(business_id=business_id, pincode=pincode))
    await session.flush()
    return wanted


async def assign_categories(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    category_ids: list[uuid.UUID],
) -> list[uuid.UUID]:
    wanted = set(category_ids)
    await get_owned_business(session, owner_user_id, business_id)
    known = (
        set((await session.scalars(select(Category.id).where(Category.id.in_(wanted)))).all())
        if wanted
        else set()
    )
    unknown = wanted - known
    if unknown:
        raise ValueError(f"unknown categories: {sorted(str(u) for u in unknown)}")
    existing = set(
        (
            await session.scalars(
                select(BusinessCategory.category_id).where(
                    BusinessCategory.business_id == business_id
                )
            )
        ).all()
    )
    stale = existing - wanted
    if stale:
        await session.execute(
            delete(BusinessCategory).where(
                BusinessCategory.business_id == business_id,
                BusinessCategory.category_id.in_(stale),
            )
        )
    for category_id in wanted - existing:
        session.add(BusinessCategory(business_id=business_id, category_id=category_id))
    await session.flush()
    return sorted(wanted)


async def list_categories(
    session: AsyncSession, *, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
) -> Page[Category]:
    return await paginate(session, select(Category), cursor=cursor, limit=limit)


async def get_by_slug_any_status(session: AsyncSession, slug: str) -> Business | None:
    """Enforcement-state lookup for the public 410 branch (M1.5). Soft-deleted
    rows stay invisible via the ORM listener; suspended/disabled are returned."""
    business: Business | None = await session.scalar(select(Business).where(Business.slug == slug))
    return business


async def get_by_slug(
    session: AsyncSession, slug: str
) -> tuple[Business, list[Branch], list[Category]] | None:
    """Public detail bundle. Suspended and soft-deleted businesses are hidden."""
    business = await session.scalar(
        select(Business).where(Business.slug == slug, Business.status == "active")
    )
    if business is None:
        return None
    branches = list(
        (
            await session.scalars(
                select(Branch).where(Branch.business_id == business.id).order_by(Branch.id)
            )
        ).all()
    )
    categories = list(
        (
            await session.scalars(
                select(Category)
                .join(BusinessCategory, BusinessCategory.category_id == Category.id)
                .where(BusinessCategory.business_id == business.id)
                .order_by(Category.sort_order)
            )
        ).all()
    )
    return business, branches, categories
