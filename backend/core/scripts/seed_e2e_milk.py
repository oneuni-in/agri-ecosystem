"""Idempotent E2E seed (D23): ensure a milk vendor covers 641001 so the
milk-home 'covered' branch renders deterministically. Safe to run repeatedly
(checks by business name before creating anything). Mirrors
scripts/make_business.py's create_business -> add_branch -> set_coverage ->
catalog_service.create_product -> moderate_product(approve=True) sequence.

The owner is a real identity.User, minted via modules.identity.service so it
satisfies users.agri_id (NOT NULL/UNIQUE, no default) - there is no `handle`
column on User, and constructing one by hand would either miss agri_id or
reinvent the AG- fallback sequence that create_user() already owns.
Business.owner_user_id itself is never an FK into identity (module
independence contract - see directory/models.py), so this is a convenience
choice, not a hard requirement; get_by_phone() reuses the row across runs
(and across scripts/make_business.py) instead of minting a duplicate.

Run:
    cd backend/core
    .venv/Scripts/python.exe scripts/seed_e2e_milk.py
"""

import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service, service
from modules.directory.models import Branch, Business
from modules.identity import service as identity_service
from modules.identity.models import Role, UserRole
from shared.db import get_sessionmaker
from shared.dev_only import refuse_in_prod

_OWNER_PHONE = "+919000000023"
_BUSINESS_NAME = "E2E Milk Vendor"
_PINCODE = "641001"
# The 641001 centroid, deliberately. D29 tried moving this fixture off-centre
# to stop map markers overlapping and that was WRONG twice over:
#   - overlap is not positional. VendorMap called fitBounds() before the style
#     loaded, so it silently no-op'd and the map sat at world zoom with every
#     pin inside 0.007px of every other. Fixed in vendor-map.tsx instead.
#   - covers() fans a need out to the nearest need_fanout_limit (10) businesses
#     and the D27 demo import puts FIFTY covering businesses on this pincode,
#     most at distance 0. Moving the fixture 532m out dropped it to ~rank 30,
#     so post-need.spec.ts stopped receiving its own inquiry.
# Distance 0 keeps the fixture first in every nearest-first ordering, which is
# what the journey specs rely on. map-sync.spec.ts handles stacking by clicking
# the topmost (last-rendered) pin rather than by demanding a unique position.
_BRANCH_LAT = Decimal("10.923220")
_BRANCH_LNG = Decimal("76.968600")

_STAFF_PHONE = "+919000000029"
_CLAIMABLE_NAME = "E2E Claimable Dairy"
_CLAIMABLE_LAT = Decimal("10.923220")
_CLAIMABLE_LNG = Decimal("76.968600")
_PRODUCTS = [
    (
        "Fresh Cow Milk",
        {"category": "milk", "milk_type": "cow", "fat_percent": 4.2, "pack_size": "1l"},
        "₹55/L",
    ),
    (
        "Buffalo Milk",
        {"category": "milk", "milk_type": "buffalo", "fat_percent": 6.5, "pack_size": "1l"},
        "₹70/L",
    ),
]


async def _ensure_staff(session: AsyncSession) -> None:
    """Staff identity for the D29 moderation steps (claim approve, review
    approve). modules.directory's admin routers are ROLE-gated on
    staff/super_admin - import-linter forbids importing modules.identity there,
    so require_permission is unavailable - which means a scoped role grant is
    all this needs. Unlike the FIRST super_admin, no SQL bootstrap is involved.

    assign_role() always INSERTs and user_roles carries a
    UniqueConstraint(user_id, role_id), so re-running would raise; check first
    rather than catching IntegrityError, which would poison the session."""
    user = await identity_service.get_by_phone(session, _STAFF_PHONE)
    if user is None:
        user = await identity_service.create_user(session, _STAFF_PHONE)

    role = await session.scalar(select(Role).where(Role.name == "staff"))
    if role is None:
        raise RuntimeError("role 'staff' missing - run `alembic upgrade head` (migration 0008)")
    held = await session.scalar(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
    )
    if held is None:
        await identity_service.assign_role(session, user.id, "staff")
        await session.commit()
        print(f"seed_e2e_milk: granted staff to {_STAFF_PHONE}")  # noqa: T201
    else:
        await session.commit()  # the create_user above may still be pending


async def _ensure_claimable(session: AsyncSession) -> None:
    """A NULL-owner business at 641001 - D16's definition of claimable
    (claims.py refuses when owner_user_id is not None). create_business and the
    owner-scoped add_branch/set_coverage all require an owner, so mint it with
    the usual seed owner and null the column afterwards, before commit."""
    existing = await session.scalar(select(Business).where(Business.name == _CLAIMABLE_NAME))
    if existing is not None:
        branch = await session.scalar(select(Branch).where(Branch.business_id == existing.id))
        if branch is not None and (branch.lat != _CLAIMABLE_LAT or branch.lng != _CLAIMABLE_LNG):
            branch.lat = _CLAIMABLE_LAT
            branch.lng = _CLAIMABLE_LNG
            await session.commit()
        if existing.owner_user_id is not None:
            # a previous e2e run approved a claim on it - reset so the journey
            # stays repeatable without a DB wipe
            existing.owner_user_id = None
            await session.commit()
            print("seed_e2e_milk: reset claimable owner")  # noqa: T201
        return

    placeholder = await identity_service.get_by_phone(session, _OWNER_PHONE)
    if placeholder is None:
        placeholder = await identity_service.create_user(session, _OWNER_PHONE)

    business = await service.create_business(
        session,
        owner_user_id=placeholder.id,
        name=_CLAIMABLE_NAME,
        type_="vendor",
        primary_pincode=_PINCODE,
        description={"en": "Unclaimed listing for the D29 claim journey."},
    )
    await service.add_branch(
        session,
        owner_user_id=placeholder.id,
        business_id=business.id,
        address="2 E2E Road",
        state="Tamil Nadu",
        district="Coimbatore",
        pincode=_PINCODE,
        lat=_CLAIMABLE_LAT,
        lng=_CLAIMABLE_LNG,
    )
    # Deliberately NO set_coverage: coverage is what puts a business into the
    # D25 need fan-out, and in CI only two businesses cover 641001, so giving
    # this one coverage would route half of every posted need to a NULL-owner
    # listing nobody can answer. Claiming is slug-addressed and needs none of it.
    business.owner_user_id = None  # claimable, AFTER the owner-scoped writes
    slug = business.slug
    await session.commit()
    print(f"seed_e2e_milk: created claimable {slug}")  # noqa: T201


async def run() -> None:
    refuse_in_prod("seed_e2e_milk.py")
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing = await session.scalar(select(Business).where(Business.name == _BUSINESS_NAME))
        if existing is not None:
            branch = await session.scalar(select(Branch).where(Branch.business_id == existing.id))
            # reconcile, don't merely backfill nulls: a DB seeded before the
            # centroid-collision fix still carries the OLD coordinates, and a
            # null-only check would leave them there forever
            if branch is not None and (branch.lat != _BRANCH_LAT or branch.lng != _BRANCH_LNG):
                branch.lat = _BRANCH_LAT
                branch.lng = _BRANCH_LNG
                await session.commit()
                print("seed_e2e_milk: reconciled branch coords")  # noqa: T201
            else:
                print("seed_e2e_milk: already present, nothing to do")  # noqa: T201
            await _ensure_staff(session)
            await _ensure_claimable(session)
            return

        owner = await identity_service.get_by_phone(session, _OWNER_PHONE)
        if owner is None:
            owner = await identity_service.create_user(session, _OWNER_PHONE)

        business = await service.create_business(
            session,
            owner_user_id=owner.id,
            name=_BUSINESS_NAME,
            type_="vendor",
            primary_pincode=_PINCODE,
            description={"en": "Deterministic E2E milk vendor."},
        )
        await service.add_branch(
            session,
            owner_user_id=owner.id,
            business_id=business.id,
            address="1 E2E Road",
            state="Tamil Nadu",
            district="Coimbatore",
            pincode=_PINCODE,
            lat=_BRANCH_LAT,
            lng=_BRANCH_LNG,
            # seed dev contact numbers so the D18 contact-reveal flow returns
            # something (real listings get these via the D16 claim flow)
            phone="+919876500023",
            whatsapp="+919876500023",
        )
        await service.set_coverage(
            session, owner_user_id=owner.id, business_id=business.id, pincodes=[_PINCODE]
        )
        for name, specs, price in _PRODUCTS:
            product = await catalog_service.create_product(
                session,
                owner_user_id=owner.id,
                business_id=business.id,
                vertical_slug="milk",
                name=name,
                specs=specs,
                price_display=price,
            )
            # products default to pending; approve so milk_home() surfaces it
            await catalog_service.moderate_product(session, product_id=product.id, approve=True)

        slug = business.slug
        await session.commit()
        print(f"seed_e2e_milk: created {slug}")  # noqa: T201

        await _ensure_staff(session)
        await _ensure_claimable(session)


if __name__ == "__main__":
    asyncio.run(run())
