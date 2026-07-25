"""Vertical schema fetch (D26 products console): the create form needs the
active field defs BEFORE any product exists."""

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio

# Seeding: the "milk" vertical + its v1 schema (3 fields: milk_type,
# fat_percent, pack_size) are seeded by migration 0018 itself (see
# tests/test_catalog_router.py / test_catalog_admin.py, which both use
# vertical_slug="milk" directly with no per-test Vertical row). db_session
# rolls back to that baseline after every test, so publishing a v2 here below
# is exactly what proves "active" means the highest version, not just
# whatever the migration seeded.


async def _seed_milk_vertical(session: AsyncSession) -> None:
    """Publish milk schema v2 on top of the migration-seeded v1, so the route
    under test has to pick the ACTIVE (highest) version, not just v1."""
    await catalog_service.create_schema_version(
        session,
        vertical_slug="milk",
        fields_raw=[
            {
                "key": "qty",
                "label": {"en": "Quantity"},
                "type": "number",
                "min": 0,
                "max": 100,
                "required": False,
            }
        ],
    )
    await session.flush()


async def test_returns_active_schema_fields(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _seed_milk_vertical(session)
    response = await http.get("/catalog/verticals/milk/schema", headers=_as(uuid.uuid4()))
    assert response.status_code == 200
    body = response.json()
    assert body["vertical_slug"] == "milk"
    assert body["version"] == 2
    assert isinstance(body["fields"], list) and body["fields"]
    assert body["fields"][0]["key"] == "qty"


async def test_unknown_vertical_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _session = api
    response = await http.get("/catalog/verticals/nope/schema", headers=_as(uuid.uuid4()))
    assert response.status_code == 404


async def test_requires_auth(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _session = api
    response = await http.get("/catalog/verticals/milk/schema")
    assert response.status_code == 401
