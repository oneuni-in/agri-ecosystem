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

from sqlalchemy import select

from modules.directory import catalog_service, service
from modules.directory.models import Business
from modules.identity import service as identity_service
from shared.db import get_sessionmaker

_OWNER_PHONE = "+919000000023"
_BUSINESS_NAME = "E2E Milk Vendor"
_PINCODE = "641001"
_PRODUCTS = [
    ("Fresh Cow Milk", {"milk_type": "cow", "fat_percent": 4.2, "pack_size": "1l"}, "₹55/L"),
    ("Buffalo Milk", {"milk_type": "buffalo", "fat_percent": 6.5, "pack_size": "1l"}, "₹70/L"),
]


async def run() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing = await session.scalar(select(Business).where(Business.name == _BUSINESS_NAME))
        if existing is not None:
            print("seed_e2e_milk: already present, nothing to do")  # noqa: T201
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


if __name__ == "__main__":
    asyncio.run(run())
