"""Owner billing routes: flag-off 404s, ownership is not an oracle (404 for
someone else's business), create -> checkout URL, invoice pagination."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.billing import razorpay_client
from modules.billing.models import Invoice, Subscription
from modules.directory.models import Business
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache
from shared.security import register_principal_resolver
from tests.fixtures.billing import FakeRazorpay

pytestmark = pytest.mark.asyncio

OWNER = uuid.uuid4()
STRANGER = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...] = ("user",)) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str = "user") -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


@pytest.fixture
async def api(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay]]:
    fake = FakeRazorpay()
    monkeypatch.setattr(razorpay_client, "get_client", lambda: fake)
    monkeypatch.setenv("RAZORPAY_PLAN_ID_GROWTH", "plan_growth")
    monkeypatch.setenv("RAZORPAY_PLAN_ID_PRO", "plan_pro")
    from settings import get_settings

    get_settings.cache_clear()
    app = create_app()

    async def _resolver(request: Request, session: AsyncSession) -> _Principal | None:
        header = request.headers.get("x-test-user")
        if header is None:
            return None
        roles = tuple(request.headers.get("x-test-roles", "user").split(","))
        return _Principal(uuid.UUID(header), roles)

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


async def _seed_business(session: AsyncSession, owner: uuid.UUID = OWNER) -> Business:
    business = Business(
        name="Kovai Mills",
        slug=f"kovai-{uuid.uuid4().hex[:8]}",
        owner_user_id=owner,
        type="farm",
        primary_pincode="641001",
    )
    session.add(business)
    await session.flush()
    return business


async def test_flag_off_all_owner_routes_404(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    business = await _seed_business(session)
    cases: list[tuple[str, str, dict[str, Any]]] = [
        (
            "POST",
            "/billing/subscriptions",
            {"json": {"business_id": str(business.id), "tier": "growth"}},
        ),
        ("GET", "/billing/subscription", {}),
        ("GET", "/billing/invoices", {}),
    ]
    for method, path, kwargs in cases:
        response = await client.request(method, path, headers=_as(OWNER), **kwargs)
        assert response.status_code == 404, path
    assert fake.calls == []  # zero live calls while dark


async def test_create_subscription_happy_path(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    response = await client.post(
        "/billing/subscriptions",
        json={"business_id": str(business.id), "tier": "growth"},
        headers=_as(OWNER),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["checkout_url"].startswith("https://rzp.io/i/")
    assert body["subscription"]["tier"] == "growth"
    assert body["subscription"]["status"] == "active"
    assert body["subscription"]["current_period_end"] is None  # pre-first-charge shape
    assert ("create", "sub_000001") in fake.calls


async def test_create_rejects_foreign_business_and_duplicates(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    foreign = await client.post(
        "/billing/subscriptions",
        json={"business_id": str(business.id), "tier": "growth"},
        headers=_as(STRANGER),
    )
    assert foreign.status_code == 404  # not-yours == not-found, no IDOR oracle
    first = await client.post(
        "/billing/subscriptions",
        json={"business_id": str(business.id), "tier": "growth"},
        headers=_as(OWNER),
    )
    assert first.status_code == 201
    duplicate = await client.post(
        "/billing/subscriptions",
        json={"business_id": str(business.id), "tier": "pro"},
        headers=_as(OWNER),
    )
    assert duplicate.status_code == 409


async def test_unknown_tier_422_unconfigured_plan_503(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    bad_tier = await client.post(
        "/billing/subscriptions",
        json={"business_id": str(business.id), "tier": "diamond"},
        headers=_as(OWNER),
    )
    assert bad_tier.status_code == 422
    monkeypatch.delenv("RAZORPAY_PLAN_ID_GROWTH")
    from settings import get_settings

    get_settings.cache_clear()
    unconfigured = await client.post(
        "/billing/subscriptions",
        json={"business_id": str(business.id), "tier": "growth"},
        headers=_as(OWNER),
    )
    assert unconfigured.status_code == 503


async def test_my_subscription_and_invoices(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    sub = Subscription(business_id=business.id, tier="pro", razorpay_sub_id="sub_view")
    session.add(sub)
    await session.flush()
    for index in range(3):
        session.add(
            Invoice(
                subscription_id=sub.id,
                amount_paise=149900,
                status="paid",
                razorpay_invoice_id=f"inv_view_{index}",
            )
        )
    await session.flush()

    mine = await client.get("/billing/subscription", headers=_as(OWNER))
    assert mine.status_code == 200
    body = mine.json()
    assert body["subscription"]["tier"] == "pro"
    assert body["business_name"] == "Kovai Mills"
    assert {tier["key"] for tier in body["tiers"]} == {"growth", "pro"}

    empty = await client.get("/billing/subscription", headers=_as(STRANGER))
    assert empty.status_code == 200 and empty.json()["subscription"] is None

    page_one = await client.get("/billing/invoices?limit=2", headers=_as(OWNER))
    assert page_one.status_code == 200
    assert len(page_one.json()["items"]) == 2
    cursor = page_one.json()["next_cursor"]
    assert cursor
    page_two = await client.get(f"/billing/invoices?limit=2&cursor={cursor}", headers=_as(OWNER))
    assert len(page_two.json()["items"]) == 1
    assert page_two.json()["next_cursor"] is None
