import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory.leads_models import PincodeInterest
from shared.db import get_session
from shared.security import register_principal_resolver


class _Principal:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.roles = ("user",)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        return _Principal(uuid.UUID(header)) if header else None

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as http:
        yield http


@pytest.mark.asyncio
async def test_pincode_interest_row_roundtrips(db_session):
    row = PincodeInterest(
        pincode="641001",
        district="Coimbatore",
        contact="+919876500001",
        from_user_id=None,
        milk_type="cow",
    )
    db_session.add(row)
    await db_session.flush()

    fetched = await db_session.scalar(select(PincodeInterest).where(PincodeInterest.id == row.id))
    assert fetched is not None
    assert isinstance(fetched.id, uuid.UUID)  # UUIDv7 PK auto-assigned
    assert fetched.pincode == "641001"
    assert fetched.district == "Coimbatore"
    assert fetched.from_user_id is None
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_post_pincode_interest_anonymous_tn(client, tn_geo_sample):
    resp = await client.post(
        "/leads/pincode-interest",
        json={"pincode": "641001", "contact": "+919876500001", "milk_type": "cow"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["pincode"] == "641001"
    assert body["district"] == "Coimbatore"  # derived from geo (TN)


@pytest.mark.asyncio
async def test_post_pincode_interest_non_tn_has_null_district(client, tn_geo_sample):
    resp = await client.post("/leads/pincode-interest", json={"pincode": "110001"})
    assert resp.status_code == 201
    assert resp.json()["district"] is None  # non-TN: geo cannot resolve a district


@pytest.mark.asyncio
async def test_post_pincode_interest_bad_pincode_422(client):
    resp = await client.post("/leads/pincode-interest", json={"pincode": "64100"})
    assert resp.status_code == 422
