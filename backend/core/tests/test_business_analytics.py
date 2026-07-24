"""Owner analytics (D26.D): correct source split (views / reveal-attribution
/ real leads), pincode grouping, day windowing, owner-only access."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from modules.directory.leads_models import Inquiry, InquiryResponse
from modules.directory.models import ProfileView
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _business(session: AsyncSession, owner: uuid.UUID) -> uuid.UUID:
    business = await service.create_business(
        session,
        owner_user_id=owner,
        name="Stats Dairy",
        type_="vendor",
        primary_pincode="641001",
    )
    await session.commit()
    return business.id


def _view(business_id: uuid.UUID, pincode: str | None, days_ago: int, tag: str) -> ProfileView:
    return ProfileView(
        business_id=business_id,
        pincode=pincode,
        viewer_hash=f"hash-{tag}",
        occurred_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


async def test_analytics_splits_sources_and_groups_by_pincode(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    session.add_all(
        [
            _view(business_id, "641001", 1, "a"),
            _view(business_id, "641001", 2, "b"),
            _view(business_id, None, 1, "c"),
            _view(business_id, "641001", 60, "old"),  # outside 30d window
        ]
    )
    session.add(  # reveal-attribution inquiry (counts as reveal, NOT lead)
        Inquiry(
            type="contact",
            from_user_id=uuid.uuid4(),
            business_id=business_id,
            payload={"message": "x", "source": "contact_reveal"},
            pincode="641001",
        )
    )
    session.add(  # a real lead
        Inquiry(
            type="milk_subscription",
            from_user_id=uuid.uuid4(),
            business_id=business_id,
            payload={"qty_liters": 2, "milk_type": "cow", "schedule": "daily"},
            pincode="641002",
        )
    )
    await session.commit()
    response = await http.get(
        f"/directory/businesses/{business_id}/analytics?days=30", headers=_as(owner)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["days"] == 30
    assert body["views"]["total"] == 3
    assert body["views"]["by_pincode"] == [
        {"pincode": "641001", "count": 2},
        {"pincode": "unknown", "count": 1},
    ]
    assert body["reveals"]["total"] == 1
    assert body["reveals"]["by_pincode"] == [{"pincode": "641001", "count": 1}]
    assert body["leads"]["total"] == 1
    assert body["leads"]["by_pincode"] == [{"pincode": "641002", "count": 1}]
    assert body["response"]["total"] == 2  # reveal-attribution rows sit in the inbox too


async def test_response_time_stat_is_accurate(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """NN#3: exact avg over seeded deltas (600s and 1200s -> 900s)."""
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    base = datetime.now(UTC) - timedelta(days=1)
    for offset_s in (600, 1200):
        inquiry = Inquiry(
            type="contact",
            from_user_id=uuid.uuid4(),
            business_id=business_id,
            payload={"message": "hello"},
            pincode="641001",
            status="responded",
        )
        session.add(inquiry)
        await session.flush()
        # pin created_at explicitly so the delta is exact
        inquiry.created_at = base
        session.add(
            InquiryResponse(
                inquiry_id=inquiry.id,
                business_user_id=owner,
                body="reply",
            )
        )
        await session.flush()
        response_row = (
            await session.scalars(
                select(InquiryResponse).where(InquiryResponse.inquiry_id == inquiry.id)
            )
        ).one()
        response_row.created_at = base + timedelta(seconds=offset_s)
    await session.commit()
    result = await http.get(
        f"/directory/businesses/{business_id}/analytics?days=7", headers=_as(owner)
    )
    assert result.status_code == 200
    assert result.json()["response"]["avg_response_seconds"] == 900


async def test_analytics_idor_is_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    business_id = await _business(session, uuid.uuid4())
    response = await http.get(
        f"/directory/businesses/{business_id}/analytics", headers=_as(uuid.uuid4())
    )
    assert response.status_code == 404


async def test_bad_days_rejected(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.get(
        f"/directory/businesses/{business_id}/analytics?days=14", headers=_as(owner)
    )
    assert response.status_code == 422
