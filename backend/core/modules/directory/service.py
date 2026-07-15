"""Directory service layer (D15). Every write is owner-scoped through
owned_by(column="owner_user_id"); a non-owner gets BusinessNotFoundError,
which the router maps to the same 404 as a missing row (IDOR threat model).

Never log request bodies here - business contact PII flows through this module.
"""

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.models import Business
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
MUTABLE_FIELDS = {"name", "type", "primary_pincode", "description"}


class BusinessNotFoundError(Exception):
    """No such business - or not yours. The router 404s both identically."""


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
