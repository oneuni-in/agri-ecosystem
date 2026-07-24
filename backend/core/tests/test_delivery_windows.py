"""Delivery windows (D26.A): owner-editable via PATCH, validated shape,
served on the public business detail."""

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _business(session: AsyncSession, owner: uuid.UUID) -> uuid.UUID:
    business = await service.create_business(
        session, owner_user_id=owner, name="Window Dairy", type_="vendor",
        primary_pincode="641001",
    )
    await session.commit()
    return business.id


WINDOW = {"days": ["mon", "tue", "wed"], "open": "06:00", "close": "09:30"}


async def test_patch_sets_delivery_windows(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.patch(
        f"/directory/businesses/{business_id}",
        json={"delivery_windows": [WINDOW]},
        headers=_as(owner),
    )
    assert response.status_code == 200
    assert response.json()["delivery_windows"] == [WINDOW]


async def test_public_detail_serves_windows(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    await http.patch(
        f"/directory/businesses/{business_id}",
        json={"delivery_windows": [WINDOW]},
        headers=_as(owner),
    )
    business = await service.get_owned_business(session, owner, business_id)
    detail = await http.get(f"/directory/businesses/{business.slug}")
    assert detail.status_code == 200
    assert detail.json()["business"]["delivery_windows"] == [WINDOW]


@pytest.mark.parametrize(
    "bad",
    [
        {"days": ["funday"], "open": "06:00", "close": "09:00"},   # unknown day
        {"days": ["mon"], "open": "25:00", "close": "26:00"},      # bad time
        {"days": ["mon"], "open": "09:00", "close": "06:00"},      # open >= close
        {"days": ["mon"], "open": "09:00", "close": "09:00"},      # zero-length
        {"days": [], "open": "06:00", "close": "09:00"},           # no days
    ],
)
async def test_invalid_windows_rejected(api: tuple[httpx.AsyncClient, AsyncSession], bad: dict) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.patch(
        f"/directory/businesses/{business_id}",
        json={"delivery_windows": [bad]},
        headers=_as(owner),
    )
    assert response.status_code == 422


async def test_more_than_seven_windows_rejected(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.patch(
        f"/directory/businesses/{business_id}",
        json={"delivery_windows": [WINDOW] * 8},
        headers=_as(owner),
    )
    assert response.status_code == 422
