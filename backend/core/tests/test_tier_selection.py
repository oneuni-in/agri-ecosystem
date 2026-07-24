"""Tier selection (D26): records INTENT only. subscription_tier is never
touched by the owner surface (fake-premium threat model); IDOR contract:
someone else's business == 404."""

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _business(session: AsyncSession, owner: uuid.UUID) -> uuid.UUID:
    business = await service.create_business(
        session, owner_user_id=owner, name="Tier Dairy", type_="vendor", primary_pincode="641001"
    )
    await session.commit()
    return business.id


async def test_select_premium_records_intent_only(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "premium"},
        headers=_as(owner),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["subscription_tier"] == "free"  # NOT premium - intent only
    assert body["premium_requested_at"] is not None


async def test_select_free_clears_intent(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "premium"},
        headers=_as(owner),
    )
    response = await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "free"},
        headers=_as(owner),
    )
    assert response.status_code == 200
    assert response.json()["premium_requested_at"] is None


async def test_tier_selection_idor_is_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    business_id = await _business(session, uuid.uuid4())
    response = await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "premium"},
        headers=_as(uuid.uuid4()),  # a different user
    )
    assert response.status_code == 404


async def test_tier_selection_requires_auth(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    business_id = await _business(session, uuid.uuid4())
    response = await http.put(
        f"/directory/businesses/{business_id}/tier-selection", json={"tier": "premium"}
    )
    assert response.status_code == 401


async def test_garbage_tier_is_422(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    response = await http.put(
        f"/directory/businesses/{business_id}/tier-selection",
        json={"tier": "platinum"},
        headers=_as(owner),
    )
    assert response.status_code == 422


async def test_patch_cannot_change_subscription_tier(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Regression pin for the one-way door. Whether Pydantic ignores the
    unknown key (200) or rejects it, the tier must remain free."""
    http, session = api
    owner = uuid.uuid4()
    business_id = await _business(session, owner)
    await http.patch(
        f"/directory/businesses/{business_id}",
        json={"subscription_tier": "premium"},
        headers=_as(owner),
    )
    business = await service.get_owned_business(session, owner, business_id)
    assert business.subscription_tier == "free"
