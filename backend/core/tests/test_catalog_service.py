"""Catalog registry + schema-version service (D17): active-only vertical
listing, MAX(version) resolution, append-only schema creation validated
through modules.directory.specs.parse_fields."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service, service
from modules.directory.catalog_models import Vertical
from modules.directory.models import Business
from modules.directory.specs import SpecValidationError

pytestmark = pytest.mark.asyncio

MILK_V2_EXTRA = {
    "key": "source_farm",
    "label": {"en": "Source farm"},
    "type": "string",
    "required": True,
}


async def _business(session: AsyncSession, owner: uuid.UUID) -> Business:
    return await service.create_business(
        session,
        owner_user_id=owner,
        name="Coimbatore Dairy",
        type_="vendor",
        primary_pincode="641001",
    )


async def test_active_schema_is_highest_version(db_session: AsyncSession) -> None:
    # M1 (0029) seeded a real v2 - assert MAX(version) resolution relative
    # to whatever is active, not a hardcoded absolute version number.
    base = await catalog_service.active_schema(db_session, "milk")
    assert base is not None
    starting_version = base.version
    v_next = await catalog_service.create_schema_version(
        db_session,
        vertical_slug="milk",
        fields_raw=[
            *base.fields,
            {"key": "source_farm", "label": {"en": "Source farm"}, "type": "string"},
        ],
    )
    assert v_next.version == starting_version + 1
    latest = await catalog_service.active_schema(db_session, "milk")
    assert latest is not None
    assert latest.version == starting_version + 1


async def test_create_schema_version_validates_fields(db_session: AsyncSession) -> None:
    with pytest.raises(SpecValidationError) as exc_info:
        await catalog_service.create_schema_version(
            db_session, vertical_slug="milk", fields_raw=[{"key": "Bad!"}]
        )
    assert exc_info.value.code == "invalid_field_definition"


async def test_create_schema_version_unknown_vertical(db_session: AsyncSession) -> None:
    with pytest.raises(catalog_service.VerticalNotFoundError):
        await catalog_service.create_schema_version(
            db_session,
            # A slug 0037's agri seed can never claim ("tractors" now exists)
            vertical_slug="no-such-vertical",
            fields_raw=[{"key": "hp", "label": {"en": "HP"}, "type": "number"}],
        )


async def test_list_verticals_hides_hidden(db_session: AsyncSession) -> None:
    db_session.add(Vertical(slug="hidden-v", name={"en": "Hidden"}, status="hidden"))
    await db_session.flush()
    # Membership, not the exact list: 0037 seeded the 36 agri verticals, so
    # the registry is no longer just ["milk"]. What this test protects is
    # unchanged — hidden rows never surface.
    page = await catalog_service.list_verticals(db_session, limit=100)
    slugs = [v.slug for v in page.items]
    assert "milk" in slugs
    assert "hidden-v" not in slugs
    assert all(v.status == "active" for v in page.items)


async def test_create_product_pins_active_version(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    active = await catalog_service.active_schema(db_session, "milk")
    assert active is not None
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="A2 Full Cream",
        specs={
            "category": "milk",
            "milk_type": "a2",
            "fat_percent": 4.5,
            "pack_size": "500ml",
        },
        price_display="₹80/500ml",
    )
    assert product.schema_version == active.version
    assert product.moderation_status == "pending"  # UGC default
    assert product.slug == "a2-full-cream"


async def test_create_product_rejects_bad_specs(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    with pytest.raises(SpecValidationError) as exc_info:
        await catalog_service.create_product(
            db_session,
            owner_user_id=owner,
            business_id=business.id,
            vertical_slug="milk",
            name="Goat Milk",
            specs={"category": "milk", "milk_type": "goat"},
        )
    assert exc_info.value.code == "invalid_enum_value"
    with pytest.raises(SpecValidationError) as exc_info:
        await catalog_service.create_product(
            db_session,
            owner_user_id=owner,
            business_id=business.id,
            vertical_slug="milk",
            name="Hacked",
            specs={"category": "milk", "hacked": 1, "milk_type": "cow"},
        )
    assert exc_info.value.code == "unknown_field"


async def test_create_product_owner_scoped_idor(db_session: AsyncSession) -> None:
    owner_a, owner_b = uuid.uuid4(), uuid.uuid4()
    business = await _business(db_session, owner_a)
    with pytest.raises(service.BusinessNotFoundError):
        await catalog_service.create_product(
            db_session,
            owner_user_id=owner_b,
            business_id=business.id,
            vertical_slug="milk",
            name="Stolen",
            specs={"category": "milk", "milk_type": "cow"},
        )


async def test_old_products_keep_rendering_after_schema_v2(db_session: AsyncSession) -> None:
    """NON-NEGOTIABLE 1: version pinning honored across schema evolution.

    M1 (0029) means the real "active" schema when this test starts is
    already v2 (category required) - so pinning/version-arithmetic below is
    relative to that starting point, not a hardcoded v1/v2 pair.
    """
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    schema_before = await catalog_service.active_schema(db_session, "milk")
    assert schema_before is not None
    pinned_version = schema_before.version
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="Old Toned",
        specs={"category": "milk", "milk_type": "toned"},
        price_display="₹30/500ml",
    )
    await catalog_service.moderate_product(db_session, product_id=product.id, approve=True)
    # schema evolves further: the next version adds a REQUIRED field old
    # products don't have
    await catalog_service.create_schema_version(
        db_session, vertical_slug="milk", fields_raw=[*schema_before.fields, MILK_V2_EXTRA]
    )
    next_version = pinned_version + 1
    # old product still publicly renders with its originally pinned version
    got = await catalog_service.get_public_product(db_session, product.slug)
    assert got is not None and got[0].schema_version == pinned_version
    # new writes must satisfy the newest version
    with pytest.raises(SpecValidationError) as excinfo:
        await catalog_service.create_product(
            db_session,
            owner_user_id=owner,
            business_id=business.id,
            vertical_slug="milk",
            name="New Cow",
            specs={"category": "milk", "milk_type": "cow"},
        )
    assert excinfo.value.code == "missing_required"
    # editing the old product's specs re-pins to the newest version and re-validates
    updated = await catalog_service.update_product(
        db_session,
        owner_user_id=owner,
        product_id=product.id,
        patch={"specs": {"category": "milk", "milk_type": "toned", "source_farm": "Anaimalai"}},
    )
    assert updated.schema_version == next_version


async def test_public_reads_hide_pending_archived_and_suspended(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="A2 Full Cream",
        specs={"category": "milk", "milk_type": "a2"},
    )
    # pending -> hidden
    assert await catalog_service.get_public_product(db_session, product.slug) is None
    await catalog_service.moderate_product(db_session, product_id=product.id, approve=True)
    got = await catalog_service.get_public_product(db_session, product.slug)
    assert got is not None
    assert got[0].id == product.id
    assert got[1].id == business.id
    # archived -> hidden
    await catalog_service.update_product(
        db_session, owner_user_id=owner, product_id=product.id, patch={"status": "archived"}
    )
    assert await catalog_service.get_public_product(db_session, product.slug) is None
    await catalog_service.update_product(
        db_session, owner_user_id=owner, product_id=product.id, patch={"status": "active"}
    )
    # business suspended -> hidden even though the product itself is approved/active
    business.status = "suspended"
    await db_session.flush()
    assert await catalog_service.get_public_product(db_session, product.slug) is None


async def test_no_schema_no_products(db_session: AsyncSession) -> None:
    # Own throwaway slug: "seeds" is a real registry row since 0037.
    db_session.add(Vertical(slug="seeds-nospec", name={"en": "Seeds"}, status="active"))
    await db_session.flush()
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    with pytest.raises(catalog_service.SchemaNotFoundError):
        await catalog_service.create_product(
            db_session,
            owner_user_id=owner,
            business_id=business.id,
            vertical_slug="seeds-nospec",
            name="Tomato Seeds",
            specs={},
        )


async def test_hidden_vertical_rejects_creates_and_empties_lists(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="Hidden Later",
        specs={"category": "milk", "milk_type": "cow"},
    )
    await catalog_service.moderate_product(db_session, product_id=product.id, approve=True)
    # visible while the vertical is active
    page = await catalog_service.list_vertical_products(db_session, "milk")
    assert [p.id for p in page.items] == [product.id]
    vertical = await catalog_service.get_vertical(db_session, "milk")
    assert vertical is not None
    vertical.status = "hidden"
    await db_session.flush()
    with pytest.raises(catalog_service.VerticalNotFoundError):
        await catalog_service.create_product(
            db_session,
            owner_user_id=owner,
            business_id=business.id,
            vertical_slug="milk",
            name="Nope",
            specs={"category": "milk", "milk_type": "cow"},
        )
    empty_page = await catalog_service.list_vertical_products(db_session, "milk")
    assert empty_page.items == []


async def test_slug_collision_suffixes(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    first = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="A2 Full Cream",
        specs={"category": "milk", "milk_type": "a2"},
    )
    second = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="A2 Full Cream",
        specs={"category": "milk", "milk_type": "a2"},
    )
    assert first.slug == "a2-full-cream"
    assert second.slug == "a2-full-cream-2"


async def test_update_rejects_immutable_fields(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="A2 Full Cream",
        specs={"category": "milk", "milk_type": "a2"},
    )
    for patch in ({"slug": "new-slug"}, {"business_id": uuid.uuid4()}):
        with pytest.raises(ValueError):
            await catalog_service.update_product(
                db_session, owner_user_id=owner, product_id=product.id, patch=patch
            )


async def test_image_add_remove_and_cap(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="A2 Full Cream",
        specs={"category": "milk", "milk_type": "a2"},
    )
    for i in range(catalog_service.MAX_PRODUCT_IMAGES):
        product = await catalog_service.add_product_image(
            db_session, owner_user_id=owner, product_id=product.id, key=f"products/{i}.jpg"
        )
    assert product.media_keys == [
        f"products/{i}.jpg" for i in range(catalog_service.MAX_PRODUCT_IMAGES)
    ]
    with pytest.raises(ValueError):
        await catalog_service.add_product_image(
            db_session, owner_user_id=owner, product_id=product.id, key="products/overflow.jpg"
        )
    product = await catalog_service.remove_product_image(
        db_session, owner_user_id=owner, product_id=product.id, index=0
    )
    assert product.media_keys == [
        f"products/{i}.jpg" for i in range(1, catalog_service.MAX_PRODUCT_IMAGES)
    ]
    with pytest.raises(ValueError):
        await catalog_service.remove_product_image(
            db_session, owner_user_id=owner, product_id=product.id, index=99
        )


async def test_list_my_products_shows_pending(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    first = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="First",
        specs={"category": "milk", "milk_type": "cow"},
    )
    second = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="Second",
        specs={"category": "milk", "milk_type": "buffalo"},
    )
    await catalog_service.moderate_product(db_session, product_id=second.id, approve=True)
    page = await catalog_service.list_my_products(db_session, owner, business.id, limit=1)
    assert [p.id for p in page.items] == [first.id]
    assert page.next_cursor is not None
    page2 = await catalog_service.list_my_products(
        db_session, owner, business.id, cursor=page.next_cursor
    )
    assert [p.id for p in page2.items] == [second.id]
    assert {p.moderation_status for p in (*page.items, *page2.items)} == {"pending", "approved"}
