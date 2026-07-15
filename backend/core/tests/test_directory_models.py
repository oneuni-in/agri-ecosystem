"""Directory ORM models mirror migration 0016: defaults, slug immutability,
soft-delete filtering, i18n description roundtrip."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.models import Business
from shared.db import soft_delete
from shared.slugs import ImmutableSlugError

pytestmark = pytest.mark.asyncio


def _business(slug: str) -> Business:
    return Business(
        owner_user_id=uuid.uuid4(),
        name="Milk Farm",
        slug=slug,
        type="vendor",
        primary_pincode="641001",
    )


async def test_business_roundtrip_defaults(db_session: AsyncSession) -> None:
    business = _business("models-roundtrip")
    db_session.add(business)
    await db_session.flush()
    await db_session.refresh(business)
    assert business.status == "active"
    assert business.verification_status == "unverified"
    assert business.subscription_tier == "free"
    assert business.deleted_at is None


async def test_slug_is_write_once(db_session: AsyncSession) -> None:
    business = _business("models-write-once")
    db_session.add(business)
    await db_session.flush()
    with pytest.raises(ImmutableSlugError):
        business.slug = "renamed"


async def test_soft_deleted_business_is_invisible(db_session: AsyncSession) -> None:
    business = _business("models-softdel")
    db_session.add(business)
    await db_session.flush()
    soft_delete(business)
    await db_session.flush()
    found = await db_session.scalar(select(Business).where(Business.slug == "models-softdel"))
    assert found is None


async def test_description_i18n_roundtrip(db_session: AsyncSession) -> None:
    business = _business("models-i18n")
    business.description = {"en": "Fresh milk daily", "ta": "தினமும் பசும்பால்"}
    db_session.add(business)
    await db_session.flush()
    db_session.expire(business)
    await db_session.refresh(business)
    assert business.description is not None
    assert business.description.get("en") == "Fresh milk daily"
    assert business.description.get("ta") == "தினமும் பசும்பால்"
