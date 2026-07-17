"""Catalog registry + schema-version service (D17): active-only vertical
listing, MAX(version) resolution, append-only schema creation validated
through modules.directory.specs.parse_fields."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service
from modules.directory.catalog_models import Vertical
from modules.directory.specs import SpecValidationError

pytestmark = pytest.mark.asyncio


async def test_active_schema_is_highest_version(db_session: AsyncSession) -> None:
    v1 = await catalog_service.active_schema(db_session, "milk")
    assert v1 is not None
    assert v1.version == 1
    v2 = await catalog_service.create_schema_version(
        db_session,
        vertical_slug="milk",
        fields_raw=[
            *v1.fields,
            {"key": "source_farm", "label": {"en": "Source farm"}, "type": "string"},
        ],
    )
    assert v2.version == 2
    latest = await catalog_service.active_schema(db_session, "milk")
    assert latest is not None
    assert latest.version == 2


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
            vertical_slug="tractors",
            fields_raw=[{"key": "hp", "label": {"en": "HP"}, "type": "number"}],
        )


async def test_list_verticals_hides_hidden(db_session: AsyncSession) -> None:
    db_session.add(Vertical(slug="hidden-v", name={"en": "Hidden"}, status="hidden"))
    await db_session.flush()
    page = await catalog_service.list_verticals(db_session)
    assert [v.slug for v in page.items] == ["milk"]
