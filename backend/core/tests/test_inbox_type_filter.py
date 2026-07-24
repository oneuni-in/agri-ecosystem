"""Inbox type filter (D26.B): needs arrive as milk_subscription children;
vendors filter them from plain contact leads."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.leads_models import Inquiry
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _seeded_inbox(session: AsyncSession, owner: uuid.UUID) -> uuid.UUID:
    business = await service.create_business(
        session, owner_user_id=owner, name="Inbox Dairy", type_="vendor",
        primary_pincode="641001",
    )
    session.add_all(
        [
            Inquiry(type="contact", from_user_id=uuid.uuid4(), business_id=business.id,
                    payload={"message": "hi"}, pincode="641001"),
            Inquiry(type="milk_subscription", from_user_id=uuid.uuid4(),
                    business_id=business.id,
                    payload={"qty_liters": 2, "milk_type": "cow", "schedule": "daily"},
                    pincode="641001"),
        ]
    )
    await session.commit()
    return business.id


async def test_type_filter_returns_only_matching(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _seeded_inbox(session, owner)
    response = await http.get(
        f"/leads/inbox?business_id={business_id}&type=milk_subscription", headers=_as(owner)
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "milk_subscription"


async def test_no_filter_returns_all(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _seeded_inbox(session, owner)
    response = await http.get(f"/leads/inbox?business_id={business_id}", headers=_as(owner))
    assert len(response.json()["items"]) == 2


async def test_bogus_type_422(api) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _seeded_inbox(session, owner)
    response = await http.get(
        f"/leads/inbox?business_id={business_id}&type=carrier_pigeon", headers=_as(owner)
    )
    assert response.status_code == 422
