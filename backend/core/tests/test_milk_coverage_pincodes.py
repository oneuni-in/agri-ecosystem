"""Coverage-pincodes endpoint (D28): the sitemap feed. Only pincodes that
would render an INDEXABLE landing page (milk-home scope == covered) may
appear - anything looser puts self-noindexing URLs in the sitemap."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared.db import get_session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as http:
        yield http


@pytest.mark.usefixtures("tn_geo_sample")
async def test_empty_when_no_covered_vendor(client: httpx.AsyncClient) -> None:
    res = await client.get("/catalog/milk/coverage/pincodes")
    assert res.status_code == 200
    assert res.json() == {"items": [], "next_cursor": None}


@pytest.mark.usefixtures("seed_milk_vendor")
async def test_lists_covered_pincode_with_district(client: httpx.AsyncClient) -> None:
    res = await client.get("/catalog/milk/coverage/pincodes")
    body = res.json()
    assert {"pincode": "641001", "district": "Coimbatore"} in body["items"]
    # 600001 has geo but no covering vendor -> must NOT appear
    assert all(item["pincode"] != "600001" for item in body["items"])


@pytest.mark.usefixtures("seed_milk_vendor_unapproved")
async def test_unapproved_products_do_not_index_a_pincode(client: httpx.AsyncClient) -> None:
    res = await client.get("/catalog/milk/coverage/pincodes")
    assert res.json()["items"] == []


@pytest.mark.usefixtures("seed_milk_vendor")
async def test_cursor_walk_terminates(client: httpx.AsyncClient) -> None:
    res = await client.get("/catalog/milk/coverage/pincodes", params={"limit": 1})
    body = res.json()
    assert len(body["items"]) == 1
    if body["next_cursor"]:
        res2 = await client.get(
            "/catalog/milk/coverage/pincodes",
            params={"limit": 1, "cursor": body["next_cursor"]},
        )
        assert res2.status_code == 200
        assert res2.json()["items"] != body["items"]


async def test_bad_cursor_rejected(client: httpx.AsyncClient) -> None:
    # cursor is a pincode; the route's Query pattern rejects junk with 422
    res = await client.get("/catalog/milk/coverage/pincodes", params={"cursor": "DROP TABLE"})
    assert res.status_code == 422
