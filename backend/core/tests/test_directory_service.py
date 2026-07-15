"""Directory business service: owner-scoped create/update/list (IDOR-safe),
slug generation + reservation, sanctioned rename records the 301 row."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.models import Business
from shared.db import soft_delete
from shared.slugs import SlugRedirect

pytestmark = pytest.mark.asyncio


async def _create(
    session: AsyncSession, owner: uuid.UUID, name: str = "Anbu Milk Farm"
) -> Business:
    return await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
    )


async def test_create_generates_slug_and_defaults(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _create(db_session, owner)
    assert business.slug == "anbu-milk-farm"
    assert business.owner_user_id == owner
    assert business.status == "active"
    assert business.verification_status == "unverified"


async def test_slug_collision_gets_numeric_suffix(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    first = await _create(db_session, owner)
    second = await _create(db_session, owner)
    assert first.slug == "anbu-milk-farm"
    assert second.slug == "anbu-milk-farm-2"


async def test_soft_deleted_business_keeps_its_slug_reserved(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    first = await _create(db_session, owner)
    soft_delete(first)
    await db_session.flush()
    second = await _create(db_session, owner)
    # deleted row still holds the unique slug - suffix, not IntegrityError
    assert second.slug == "anbu-milk-farm-2"


async def test_create_rejects_bad_pincode(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError):
        await service.create_business(
            db_session,
            owner_user_id=uuid.uuid4(),
            name="X",
            type_="vendor",
            primary_pincode="64100",
        )


async def test_create_rejects_unknown_locale(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError):
        await service.create_business(
            db_session,
            owner_user_id=uuid.uuid4(),
            name="X",
            type_="vendor",
            primary_pincode="641001",
            description={"fr": "lait"},
        )


async def test_update_is_owner_scoped(db_session: AsyncSession) -> None:
    owner, attacker = uuid.uuid4(), uuid.uuid4()
    business = await _create(db_session, owner)
    with pytest.raises(service.BusinessNotFoundError):
        await service.update_business(
            db_session, owner_user_id=attacker, business_id=business.id, patch={"name": "Hacked"}
        )
    updated = await service.update_business(
        db_session, owner_user_id=owner, business_id=business.id, patch={"name": "Renamed Farm"}
    )
    assert updated.name == "Renamed Farm"
    assert updated.slug == "anbu-milk-farm"  # name change never touches the slug


async def test_update_rejects_immutable_fields(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _create(db_session, owner)
    for field in ("slug", "verification_status", "subscription_tier", "owner_user_id", "status"):
        with pytest.raises(ValueError):
            await service.update_business(
                db_session, owner_user_id=owner, business_id=business.id, patch={field: "x"}
            )


async def test_list_my_businesses_only_mine(db_session: AsyncSession) -> None:
    mine_owner, other_owner = uuid.uuid4(), uuid.uuid4()
    mine = await _create(db_session, mine_owner)
    await _create(db_session, other_owner, name="Other Dairy")
    page = await service.list_my_businesses(db_session, mine_owner)
    assert [b.id for b in page.items] == [mine.id]
    assert page.next_cursor is None


async def test_rename_records_301(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _create(db_session, owner)
    await service.rename_business(
        db_session, owner_user_id=owner, business_id=business.id, new_slug="anbu-dairy"
    )
    assert business.slug == "anbu-dairy"
    redirect = (
        await db_session.scalars(
            select(SlugRedirect).where(
                SlugRedirect.old_path == "/directory/businesses/anbu-milk-farm"
            )
        )
    ).one()
    assert redirect.new_path == "/directory/businesses/anbu-dairy"


async def test_rename_is_owner_scoped(db_session: AsyncSession) -> None:
    owner, attacker = uuid.uuid4(), uuid.uuid4()
    business = await _create(db_session, owner)
    with pytest.raises(service.BusinessNotFoundError):
        await service.rename_business(
            db_session, owner_user_id=attacker, business_id=business.id, new_slug="stolen"
        )


async def test_rename_rejects_taken_or_bad_slug(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    first = await _create(db_session, owner)
    second = await _create(db_session, owner, name="Second Farm")
    with pytest.raises(ValueError):
        await service.rename_business(
            db_session, owner_user_id=owner, business_id=second.id, new_slug=first.slug
        )
    with pytest.raises(ValueError):
        await service.rename_business(
            db_session, owner_user_id=owner, business_id=second.id, new_slug="Bad Slug!"
        )
