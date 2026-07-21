"""Admin billing: super_admin-only, flag-gated, every cancel audited."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.billing import razorpay_client
from modules.billing.models import Subscription
from modules.directory.models import Business
from shared.audit import AuditEntry
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache
from shared.security import register_principal_resolver
from tests.fixtures.billing import FakeRazorpay

pytestmark = pytest.mark.asyncio

ADMIN = uuid.uuid4()
USER = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str) -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


@pytest.fixture
async def api(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay]]:
    fake = FakeRazorpay()
    monkeypatch.setattr(razorpay_client, "get_client", lambda: fake)
    app = create_app()

    async def _resolver(request: Request, session: AsyncSession) -> _Principal | None:
        header = request.headers.get("x-test-user")
        if header is None:
            return None
        return _Principal(
            uuid.UUID(header), tuple(request.headers.get("x-test-roles", "user").split(","))
        )

    register_principal_resolver(_resolver)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session, fake


async def _enable_billing(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "billing_enabled")
    assert flag is not None
    flag.enabled = True
    await session.flush()
    reset_flag_cache()


async def _seed_sub(session: AsyncSession) -> Subscription:
    business = Business(
        name="Kovai Mills",
        slug=f"kovai-{uuid.uuid4().hex[:8]}",
        owner_user_id=uuid.uuid4(),
        type="farm",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    sub = Subscription(business_id=business.id, tier="growth", razorpay_sub_id="sub_admin")
    session.add(sub)
    await session.flush()
    return sub


async def test_flag_off_admin_routes_404(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    response = await client.get("/billing/admin/subscriptions", headers=_as(ADMIN, "super_admin"))
    assert response.status_code == 404


async def test_role_gate(api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay]) -> None:
    client, session, fake = api
    await _enable_billing(session)
    response = await client.get("/billing/admin/subscriptions", headers=_as(USER, "user"))
    assert response.status_code == 403


async def test_list_and_cancel_with_audit(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    sub = await _seed_sub(session)
    fake.subs["sub_admin"] = {"id": "sub_admin", "status": "active", "current_end": None}

    listing = await client.get("/billing/admin/subscriptions", headers=_as(ADMIN, "super_admin"))
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1

    cancel = await client.post(
        f"/billing/admin/subscriptions/{sub.id}/cancel", headers=_as(ADMIN, "super_admin")
    )
    assert cancel.status_code == 200
    await session.refresh(sub)
    assert sub.status == "canceled"
    assert ("cancel", "sub_admin") in fake.calls
    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.action == "billing.admin_cancel")
    )
    assert entry is not None
    assert entry.actor_user_id == ADMIN
    assert entry.target_id == str(sub.id)

    again = await client.post(
        f"/billing/admin/subscriptions/{sub.id}/cancel", headers=_as(ADMIN, "super_admin")
    )
    assert again.status_code == 409
