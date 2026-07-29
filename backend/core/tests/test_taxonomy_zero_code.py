"""M1 NON-NEGOTIABLE 1, backend half: a value added to the schema reaches
every consumer with zero code changes. Publishing v3 in-test is the whole
proof - nothing below names the new value anywhere but the schema payload."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import catalog_service, service
from modules.directory.specs import parse_fields
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

NEW_VALUE = "shrikhand"


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        return None  # anonymous: the route under test must be public

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as http:
        yield http


async def _publish_v3(session: AsyncSession) -> None:
    """Add ONE value to the active schema and republish. This is the only
    action a real taxonomy change takes."""
    active = await catalog_service.active_schema(session, "milk")
    assert active is not None
    fields = [f.model_dump(exclude_none=True) for f in parse_fields(active.fields)]
    for field in fields:
        if field["key"] == "category":
            field["options"] = [*field["options"], NEW_VALUE]
            field["option_meta"] = {
                **field["option_meta"],
                NEW_VALUE: {
                    "label": {"en": "Shrikhand", "ta": "ஸ்ரீகண்ட்", "hi": "श्रीखंड"},
                    "icon": "shrikhand",
                },
            }
    await catalog_service.create_schema_version(session, vertical_slug="milk", fields_raw=fields)


async def test_schema_route_is_public(client: httpx.AsyncClient) -> None:
    res = await client.get("/catalog/verticals/milk/schema")
    assert res.status_code == 200
    assert res.json()["vertical_slug"] == "milk"


async def test_new_value_appears_in_the_public_schema_payload(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _publish_v3(db_session)
    res = await client.get("/catalog/verticals/milk/schema")
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == 3
    category = next(f for f in body["fields"] if f["key"] == "category")
    assert NEW_VALUE in category["options"]
    meta = category["option_meta"][NEW_VALUE]
    assert set(meta["label"]) == {"en", "ta", "hi"}
    assert meta["icon"] == "shrikhand"


async def test_new_value_appears_in_milk_home_filters(
    client: httpx.AsyncClient, db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _publish_v3(db_session)
    res = await client.get("/catalog/milk/home/641001")
    assert res.status_code == 200
    assert NEW_VALUE in res.json()["product_categories"]


async def test_new_value_is_accepted_as_a_product_spec(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    await _publish_v3(db_session)
    owner = uuid.uuid4()
    business = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Sweet Dairy",
        type_="shop",
        primary_pincode="641001",
    )
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=business.id,
        vertical_slug="milk",
        name="Elaichi Shrikhand",
        specs={"category": NEW_VALUE},
        price_display="₹80/200g",
    )
    assert product.specs["category"] == NEW_VALUE
    assert product.schema_version == 3
