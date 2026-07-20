"""GET /identity/location (D19 Task 7): profile -> GPS -> pincode -> IP ->
none resolution order (non-negotiable #2). Each rung must prove it BEATS
the rungs below it - all lower-priority signals present simultaneously,
asserting the higher rung still wins."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.models import Profile, User
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio


class _Principal:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.roles = ("user",)


def _as(user_id: uuid.UUID) -> dict[str, str]:
    return {"x-test-user": str(user_id)}


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


async def _mk_user_with_profile(
    session: AsyncSession,
    *,
    pincode: str | None,
    district: str | None,
    state: str | None,
) -> uuid.UUID:
    user = User(phone=f"+9198765{uuid.uuid4().hex[:5]}", agri_id=f"@u{uuid.uuid4().hex[:8]}")
    session.add(user)
    await session.flush()
    profile = Profile(user_id=user.id, pincode=pincode, district=district, state=state)
    session.add(profile)
    await session.flush()
    return user.id


async def test_authed_complete_profile_wins_over_gps_and_pincode(
    client: httpx.AsyncClient, db_session: AsyncSession, tn_geo_sample: None
) -> None:
    user_id = await _mk_user_with_profile(
        db_session, pincode="641001", district="Coimbatore", state="Tamil Nadu"
    )
    resp = await client.get(
        "/identity/location",
        params={"lat": 13.079, "lng": 80.287, "pincode": "600001"},
        headers=_as(user_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "profile"
    assert body["pincode"] == "641001"
    assert body["district"] == "Coimbatore"
    assert body["state"] == "Tamil Nadu"


async def test_authed_incomplete_profile_falls_through_to_gps(
    client: httpx.AsyncClient, db_session: AsyncSession, tn_geo_sample: None
) -> None:
    user_id = await _mk_user_with_profile(db_session, pincode=None, district=None, state=None)
    resp = await client.get(
        "/identity/location",
        params={"lat": 10.9232, "lng": 76.9686},
        headers=_as(user_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "gps"
    assert body["pincode"] == "641001"
    assert body["district"] == "Coimbatore"
    assert body["state"] == "Tamil Nadu"


async def test_anonymous_valid_gps_resolves_nearest_pincode(
    client: httpx.AsyncClient, tn_geo_sample: None
) -> None:
    resp = await client.get("/identity/location", params={"lat": 10.9232, "lng": 76.9686})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "gps"
    assert body["pincode"] == "641001"
    assert body["district"] == "Coimbatore"
    assert body["state"] == "Tamil Nadu"


async def test_anonymous_pincode_only_resolves(
    client: httpx.AsyncClient, tn_geo_sample: None
) -> None:
    resp = await client.get("/identity/location", params={"pincode": "641001"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "pincode"
    assert body["pincode"] == "641001"
    assert body["district"] == "Coimbatore"
    assert body["state"] == "Tamil Nadu"


async def test_anonymous_nothing_falls_to_ip_when_geoip_available(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("modules.identity.location_router.state_for_ip", lambda ip: "Tamil Nadu")
    resp = await client.get("/identity/location")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "ip"
    assert body["state"] == "Tamil Nadu"
    assert body["pincode"] is None
    assert body["district"] is None


async def test_anonymous_nothing_geoip_off_resolves_to_none(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/identity/location")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"pincode": None, "district": None, "state": None, "source": "none"}


async def test_gps_out_of_range_falls_through_to_pincode(
    client: httpx.AsyncClient, tn_geo_sample: None
) -> None:
    resp = await client.get(
        "/identity/location", params={"lat": 95, "lng": 76.9686, "pincode": "641001"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "pincode"
    assert body["pincode"] == "641001"


async def test_unknown_pincode_is_not_trusted(client: httpx.AsyncClient) -> None:
    resp = await client.get("/identity/location", params={"pincode": "999999"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"pincode": None, "district": None, "state": None, "source": "none"}
