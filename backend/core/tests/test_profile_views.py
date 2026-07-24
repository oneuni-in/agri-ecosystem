"""Profile-view beacon (D26.D): public, no PII (daily-rotating viewer hash),
DB-deduped 1/viewer/business/day, append-only storage."""

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.models import ProfileView
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _active_business(session: AsyncSession) -> tuple[uuid.UUID, str]:
    business = await service.create_business(
        session,
        owner_user_id=uuid.uuid4(),
        name="Viewed Dairy",
        type_="vendor",
        primary_pincode="641001",
    )
    await session.commit()
    return business.id, business.slug


async def test_beacon_records_view_without_auth(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    business_id, slug = await _active_business(session)
    response = await http.post(f"/directory/businesses/{slug}/view", json={"pincode": "641001"})
    assert response.status_code == 200
    rows = (await session.scalars(select(ProfileView))).all()
    assert len(rows) == 1
    assert rows[0].business_id == business_id
    assert rows[0].pincode == "641001"
    assert rows[0].viewer_hash  # never empty


async def test_same_viewer_same_day_dedupes(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    _business_id, slug = await _active_business(session)
    for _ in range(3):
        response = await http.post(f"/directory/businesses/{slug}/view", json={})
        assert response.status_code == 200  # dedupe is silent, never an error
    rows = (await session.scalars(select(ProfileView))).all()
    assert len(rows) == 1  # same transport => same ip+ua => same daily hash


async def test_unknown_slug_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _session = api
    response = await http.post("/directory/businesses/no-such-biz/view", json={})
    assert response.status_code == 404


async def test_bad_pincode_422(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    _business_id, slug = await _active_business(session)
    response = await http.post(f"/directory/businesses/{slug}/view", json={"pincode": "64100"})
    assert response.status_code == 422


async def test_viewer_hash_rotates_daily() -> None:
    from datetime import UTC, datetime

    from modules.directory import analytics

    day1 = analytics.viewer_hash("1.2.3.4", "UA", now=datetime(2026, 7, 24, tzinfo=UTC))
    day2 = analytics.viewer_hash("1.2.3.4", "UA", now=datetime(2026, 7, 25, tzinfo=UTC))
    assert day1 != day2  # unlinkable across days (DPDP-minimal)
