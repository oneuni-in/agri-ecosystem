"""Admin set-tier (D26): the ONLY subscription_tier write path. Role-gated
fail-closed; audited in the same transaction (D12 contract)."""

import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import service
from tests.d26_helpers import _as, api  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _business(session: AsyncSession) -> uuid.UUID:
    business = await service.create_business(
        session,
        owner_user_id=uuid.uuid4(),
        name="Tier Target",
        type_="vendor",
        primary_pincode="641001",
    )
    await session.commit()
    return business.id


async def test_non_admin_gets_403(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    business_id = await _business(session)
    response = await http.post(
        f"/admin/directory/businesses/{business_id}/tier",
        json={"tier": "premium"},
        headers=_as(uuid.uuid4(), roles="user"),
    )
    assert response.status_code == 403


async def test_staff_sets_premium_and_audits(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    business_id = await _business(session)
    admin = uuid.uuid4()
    response = await http.post(
        f"/admin/directory/businesses/{business_id}/tier",
        json={"tier": "premium"},
        headers=_as(admin, roles="staff"),
    )
    assert response.status_code == 200
    assert response.json()["subscription_tier"] == "premium"
    audit_row = (
        await session.execute(
            text(
                "SELECT action, actor_user_id FROM audit.entries "
                "WHERE action = 'directory.tier_set' AND target_id = :target"
            ),
            {"target": str(business_id)},
        )
    ).first()
    assert audit_row is not None


async def test_unknown_business_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _session = api
    response = await http.post(
        f"/admin/directory/businesses/{uuid.uuid4()}/tier",
        json={"tier": "premium"},
        headers=_as(uuid.uuid4(), roles="super_admin"),
    )
    assert response.status_code == 404
