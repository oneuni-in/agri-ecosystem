"""Branch/coverage/category services: parent-ownership scoping (IDOR),
declarative replace semantics, validation caps, public get_by_slug bundle."""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.models import Business, BusinessCoverage, Category
from shared.db import soft_delete

pytestmark = pytest.mark.asyncio


async def _business(
    session: AsyncSession, owner: uuid.UUID, name: str = "Anbu Milk Farm"
) -> Business:
    return await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode="641001"
    )


async def _branch_kwargs() -> dict[str, Any]:
    return {
        "address": "1 Mettupalayam Rd",
        "state": "Tamil Nadu",
        "district": "Coimbatore",
        "pincode": "641001",
    }


async def test_add_and_update_branch(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    branch = await service.add_branch(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        lat=Decimal("10.923220"),
        lng=Decimal("76.968600"),
        **(await _branch_kwargs()),
    )
    assert branch.business_id == business.id
    updated = await service.update_branch(
        db_session, owner_user_id=owner, branch_id=branch.id, patch={"phone": "+914220000000"}
    )
    assert updated.phone == "+914220000000"


async def test_branch_writes_are_owner_scoped(db_session: AsyncSession) -> None:
    owner, attacker = uuid.uuid4(), uuid.uuid4()
    business = await _business(db_session, owner)
    with pytest.raises(service.BusinessNotFoundError):
        await service.add_branch(
            db_session,
            owner_user_id=attacker,
            business_id=business.id,
            **(await _branch_kwargs()),
        )
    branch = await service.add_branch(
        db_session, owner_user_id=owner, business_id=business.id, **(await _branch_kwargs())
    )
    with pytest.raises(service.BusinessNotFoundError):
        await service.update_branch(
            db_session, owner_user_id=attacker, branch_id=branch.id, patch={"phone": "0"}
        )


async def test_set_coverage_replaces_declaratively(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    first = await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id, pincodes=["641001", "641002"]
    )
    assert first == ["641001", "641002"]
    second = await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id, pincodes=["641002", "641003"]
    )
    assert second == ["641002", "641003"]
    rows = set(
        (
            await db_session.scalars(
                select(BusinessCoverage.pincode).where(BusinessCoverage.business_id == business.id)
            )
        ).all()
    )
    assert rows == {"641002", "641003"}
    # idempotent replay
    third = await service.set_coverage(
        db_session, owner_user_id=owner, business_id=business.id, pincodes=["641002", "641003"]
    )
    assert third == ["641002", "641003"]


async def test_set_coverage_validates_and_caps(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    with pytest.raises(ValueError):
        await service.set_coverage(
            db_session, owner_user_id=owner, business_id=business.id, pincodes=["64100A"]
        )
    too_many = [f"{600000 + i}" for i in range(service.MAX_COVERAGE_PINCODES + 1)]
    with pytest.raises(ValueError):
        await service.set_coverage(
            db_session, owner_user_id=owner, business_id=business.id, pincodes=too_many
        )


async def test_set_coverage_is_owner_scoped(db_session: AsyncSession) -> None:
    owner, attacker = uuid.uuid4(), uuid.uuid4()
    business = await _business(db_session, owner)
    with pytest.raises(service.BusinessNotFoundError):
        await service.set_coverage(
            db_session, owner_user_id=attacker, business_id=business.id, pincodes=["641001"]
        )


async def test_assign_categories_replaces_and_validates(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    seeded = {
        c.slug: c.id
        for c in (
            await db_session.scalars(select(Category).where(Category.slug.in_(["farm", "dairy"])))
        ).all()
    }
    assigned = await service.assign_categories(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        category_ids=[seeded["farm"], seeded["dairy"]],
    )
    assert set(assigned) == set(seeded.values())
    narrowed = await service.assign_categories(
        db_session, owner_user_id=owner, business_id=business.id, category_ids=[seeded["dairy"]]
    )
    assert narrowed == [seeded["dairy"]]
    with pytest.raises(ValueError):
        await service.assign_categories(
            db_session, owner_user_id=owner, business_id=business.id, category_ids=[uuid.uuid4()]
        )


async def test_list_categories_returns_seeded(db_session: AsyncSession) -> None:
    page = await service.list_categories(db_session)
    slugs = {c.slug for c in page.items}
    assert {"farm", "dairy", "shop", "lab"} <= slugs


async def test_get_by_slug_bundles_and_hides(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    await service.add_branch(
        db_session, owner_user_id=owner, business_id=business.id, **(await _branch_kwargs())
    )
    farm = await db_session.scalar(select(Category).where(Category.slug == "farm"))
    assert farm is not None
    await service.assign_categories(
        db_session, owner_user_id=owner, business_id=business.id, category_ids=[farm.id]
    )
    result = await service.get_by_slug(db_session, business.slug)
    assert result is not None
    found, branches, categories = result
    assert found.id == business.id
    assert len(branches) == 1
    assert [c.slug for c in categories] == ["farm"]
    # suspended businesses are not publicly visible
    business.status = "suspended"
    await db_session.flush()
    assert await service.get_by_slug(db_session, business.slug) is None
    assert await service.get_by_slug(db_session, "no-such-slug") is None


async def test_assign_categories_is_owner_scoped(db_session: AsyncSession) -> None:
    owner, attacker = uuid.uuid4(), uuid.uuid4()
    business = await _business(db_session, owner)
    farm = await db_session.scalar(select(Category).where(Category.slug == "farm"))
    assert farm is not None
    with pytest.raises(service.BusinessNotFoundError):
        await service.assign_categories(
            db_session, owner_user_id=attacker, business_id=business.id, category_ids=[farm.id]
        )


async def test_get_by_slug_hides_soft_deleted(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    business = await _business(db_session, owner)
    result = await service.get_by_slug(db_session, business.slug)
    assert result is not None
    soft_delete(business)
    await db_session.flush()
    assert await service.get_by_slug(db_session, business.slug) is None
