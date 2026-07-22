"""Local dev helper: create a fully-searchable business owned by a phone.

There is no create-business UI yet (the web-agri /business/listings page is a
D15 stub), so this script drives the real directory.service layer to stand up
a business + branch + coverage + category for manual testing, then republishes
the search snapshot so it shows up in Meilisearch (search worker must be up).

Run:
    cd backend/core
    python -m scripts.make_business --phone +916374344282

Everything is optional except --phone; the defaults make one Coimbatore dairy
vendor on pincode 641001.
"""

import argparse
import asyncio

from sqlalchemy import select

from modules.directory import catalog_service, service
from modules.directory.models import Category
from modules.directory.search_sync import business_event_payload, product_event_payload
from modules.identity.models import User
from shared.db import get_sessionmaker
from shared.events import publish

# A few realistic milk products (mirrors data/seeds/coimbatore/products.csv).
# Every product is created then approved so it shows in the public catalog API.
DEFAULT_PRODUCTS = [
    ("Fresh Cow Milk", {"milk_type": "cow", "fat_percent": 4.2, "pack_size": "500ml"}, "₹32/500ml"),
    ("Buffalo Milk", {"milk_type": "buffalo", "fat_percent": 6.5, "pack_size": "1l"}, "₹68/1l"),
    ("A2 Cow Milk", {"milk_type": "a2", "fat_percent": 4.8, "pack_size": "500ml"}, "₹45/500ml"),
]


async def run(args: argparse.Namespace) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        owner = await session.scalar(select(User).where(User.phone == args.phone))
        if owner is None:
            raise SystemExit(
                f"no user with phone {args.phone!r} - sign up at :3003/login first"
            )

        business = await service.create_business(
            session,
            owner_user_id=owner.id,
            name=args.name,
            type_=args.type,
            primary_pincode=args.pincode,
            description={"en": args.description},
        )
        await service.add_branch(
            session,
            owner_user_id=owner.id,
            business_id=business.id,
            address=args.address,
            state="Tamil Nadu",
            district="Coimbatore",
            pincode=args.pincode,
            # seed dev contact numbers so the D18 contact-reveal flow returns
            # something (real listings get these via the D16 claim flow)
            phone=args.phone_number,
            whatsapp=args.phone_number,
        )
        await service.set_coverage(
            session,
            owner_user_id=owner.id,
            business_id=business.id,
            pincodes=[args.pincode],
        )
        category = await session.scalar(
            select(Category).where(Category.slug == args.category)
        )
        if category is not None:
            await service.assign_categories(
                session,
                owner_user_id=owner.id,
                business_id=business.id,
                category_ids=[category.id],
            )

        product_ids = []
        if not args.no_products:
            for name, specs, price in DEFAULT_PRODUCTS:
                product = await catalog_service.create_product(
                    session,
                    owner_user_id=owner.id,
                    business_id=business.id,
                    vertical_slug="milk",
                    name=name,
                    specs=specs,
                    price_display=price,
                )
                # products default to pending; approve so the public catalog lists them
                await catalog_service.moderate_product(
                    session, product_id=product.id, approve=True
                )
                product_ids.append(product.id)

        # capture payloads BEFORE commit (ORM attrs expire on commit)
        payload = await business_event_payload(session, business.id)
        product_payloads = [
            await product_event_payload(session, pid) for pid in product_ids
        ]
        slug = business.slug
        await session.commit()

    # best-effort: the search worker turns these into Meilisearch documents
    try:
        await publish("directory", "business.created", payload)
        for pp in product_payloads:
            await publish("directory", "product.created", pp)
    except Exception as exc:  # noqa: BLE001 - dev helper, never fatal
        print(f"(search publish failed, rows still created: {exc})")

    print(f"created business: {slug}  (+{len(product_payloads)} products)")
    print(f"public page:      http://localhost:3002/directory/businesses/{slug}")
    print(f"products API:     curl http://localhost:8000/catalog/businesses/{slug}/products")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phone", required=True, help="owner phone, E.164, e.g. +916374344282")
    parser.add_argument("--name", default="Sri Balaji Dairy Farm")
    parser.add_argument("--type", default="vendor", choices=["vendor", "shop", "lab", "farm"])
    parser.add_argument("--pincode", default="641001")
    parser.add_argument("--category", default="dairy")
    parser.add_argument("--address", default="12 Gandhipuram Main Road, Coimbatore")
    parser.add_argument(
        "--phone-number", default="+919876500001", help="branch contact number for reveal testing"
    )
    parser.add_argument("--description", default="Fresh farm milk, daily delivery.")
    parser.add_argument(
        "--no-products", action="store_true", help="create the business without seed products"
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
