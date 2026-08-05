"""M5 Task 9: POST/GET /billing/ad-orders - the advertiser self-serve
checkout route. Campaign fixtures are built directly via the ORM (cheaper
than driving the full quote -> create -> upload-creative -> checkout-request
wizard through modules.ads' own API; mirrors tests/test_ads_lifecycle.py's
`_campaign()` helper) since only the campaign's price snapshot + status
matter here - billing never re-derives them.

Registers the real ads<->billing seam (main.create_app wires
campaign_billing_ref into shared.lookups, same as production) so ownership/
price resolution goes through the actual resolver, not a test stub."""

import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.ads.models import Campaign
from modules.billing import razorpay_client
from modules.billing.models import AdOrder
from modules.directory.models import Business
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache
from shared.security import register_principal_resolver
from tests.fixtures.billing import FakeRazorpay

pytestmark = pytest.mark.asyncio

OWNER = uuid.uuid4()
STRANGER = uuid.uuid4()

TODAY = date(2026, 8, 5)
FLIGHT_START = TODAY - timedelta(days=1)
FLIGHT_END = TODAY + timedelta(days=14)


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
    from settings import get_settings

    get_settings.cache_clear()
    app = create_app()  # wires campaign_billing_ref into shared.lookups for real

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


def _campaign(business_id: uuid.UUID, **overrides: Any) -> Campaign:
    fields: dict[str, Any] = {
        "advertiser_business_id": business_id,
        "name": "Kharif push",
        "status": "pending_payment",
        "flight_start": FLIGHT_START,
        "flight_end": FLIGHT_END,
        "price_paise": 118_000,
        "price_subtotal_paise": 100_000,
        "price_gst_paise": 18_000,
        "pricing_model": "cpm",
        "rate_card_version": 1,
        "budget_serves_total": 5000,
    }
    fields.update(overrides)
    return Campaign(**fields)


async def _seed_campaign(
    session: AsyncSession, business_id: uuid.UUID, **overrides: Any
) -> Campaign:
    campaign = _campaign(business_id, **overrides)
    session.add(campaign)
    await session.flush()
    return campaign


# ---------------------------------------------------------------------------
# POST /billing/ad-orders


async def test_flag_off_404s_and_makes_zero_razorpay_calls(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    response = await client.post(
        "/billing/ad-orders", json={"campaign_id": str(campaign.id)}, headers=_as(OWNER)
    )
    assert response.status_code == 404
    assert fake.calls == []


async def test_checkout_happy_path_charges_exact_stored_snapshot(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)

    response = await client.post(
        "/billing/ad-orders", json={"campaign_id": str(campaign.id)}, headers=_as(OWNER)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["campaign_id"] == str(campaign.id)
    assert body["status"] == "created"
    assert body["total_paise"] == 118_000  # == campaign.price_paise, never re-derived

    order = await session.get(AdOrder, uuid.UUID(body["id"]))
    assert order is not None
    assert order.razorpay_plink_id is not None
    plink = fake.payment_links[order.razorpay_plink_id]
    assert body["checkout_url"] == plink["short_url"]
    assert plink["amount"] == 118_000  # exact charge - server snapshot, never client-suppliable
    assert plink["notes"] == {"campaign_id": str(campaign.id), "order_id": body["id"]}
    assert plink["callback_url"] == f"http://localhost:3002/business/ads?paid={campaign.id}"
    assert [c for c in fake.calls if c[0] == "create_payment_link"]

    assert order.subtotal_paise == 100_000
    assert order.gst_paise == 18_000
    assert order.total_paise == 118_000
    assert order.business_id == business.id
    assert order.razorpay_plink_id == plink["id"]
    assert order.quote["subtotal_paise"] == 100_000
    assert order.quote["gst_paise"] == 18_000
    assert order.quote["total_paise"] == 118_000

    # campaign lifecycle is untouched by billing on checkout creation - ads
    # already flipped it to pending_payment via its own checkout-request route.
    await session.refresh(campaign)
    assert campaign.status == "pending_payment"


async def test_checkout_accepts_valid_gstin(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    response = await client.post(
        "/billing/ad-orders",
        json={"campaign_id": str(campaign.id), "buyer_gstin": "29ABCDE1234F1Z5"},
        headers=_as(OWNER),
    )
    assert response.status_code == 201
    order = await session.get(AdOrder, uuid.UUID(response.json()["id"]))
    assert order is not None
    assert order.buyer_gstin == "29ABCDE1234F1Z5"


async def test_checkout_rejects_malformed_gstin(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    response = await client.post(
        "/billing/ad-orders",
        json={"campaign_id": str(campaign.id), "buyer_gstin": "not-a-gstin"},
        headers=_as(OWNER),
    )
    assert response.status_code == 422
    assert fake.calls == []


async def test_client_supplied_total_paise_is_rejected_422(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    """extra="forbid" wire-contract guard: threat model is price tampering -
    a client that tries to name its own amount is rejected outright, the
    request never reaches create_ad_order, and Razorpay is never called."""
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    response = await client.post(
        "/billing/ad-orders",
        json={"campaign_id": str(campaign.id), "total_paise": 1},
        headers=_as(OWNER),
    )
    assert response.status_code == 422
    assert fake.calls == []


async def test_foreign_campaign_is_404_not_403(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session, owner=STRANGER)
    campaign = await _seed_campaign(session, business.id)
    response = await client.post(
        "/billing/ad-orders", json={"campaign_id": str(campaign.id)}, headers=_as(OWNER)
    )
    assert response.status_code == 404  # not-yours == not-found, no IDOR oracle
    assert fake.calls == []


async def test_unknown_campaign_is_404(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    response = await client.post(
        "/billing/ad-orders", json={"campaign_id": str(uuid.uuid4())}, headers=_as(OWNER)
    )
    assert response.status_code == 404


async def test_draft_campaign_is_409_not_payable(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id, status="draft")
    response = await client.post(
        "/billing/ad-orders", json={"campaign_id": str(campaign.id)}, headers=_as(OWNER)
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "not_payable"
    assert fake.calls == []


async def test_unpriced_house_campaign_is_422_not_billable(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(
        session,
        business.id,
        status="active",
        price_paise=None,
        price_subtotal_paise=None,
        price_gst_paise=None,
        pricing_model=None,
        rate_card_version=None,
    )
    response = await client.post(
        "/billing/ad-orders", json={"campaign_id": str(campaign.id)}, headers=_as(OWNER)
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "not_billable"
    assert fake.calls == []


async def test_double_checkout_is_409_order_exists(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    first = await client.post(
        "/billing/ad-orders", json={"campaign_id": str(campaign.id)}, headers=_as(OWNER)
    )
    assert first.status_code == 201
    second = await client.post(
        "/billing/ad-orders", json={"campaign_id": str(campaign.id)}, headers=_as(OWNER)
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "order_exists"
    # both create_payment_link calls happened (order: razorpay THEN
    # savepoint-flush) - the second link is an accepted orphaned-link v1
    # trade-off, documented in modules/billing/ad_orders.py.
    assert len([c for c in fake.calls if c[0] == "create_payment_link"]) == 2
    orders = (
        await session.scalars(select(AdOrder).where(AdOrder.campaign_id == campaign.id))
    ).all()
    assert len(orders) == 1  # the loser's insert never landed


async def test_razorpay_failure_is_503_and_persists_nothing(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    fake.fail_create_payment_link = True
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    response = await client.post(
        "/billing/ad-orders", json={"campaign_id": str(campaign.id)}, headers=_as(OWNER)
    )
    assert response.status_code == 503
    orders = (
        await session.scalars(select(AdOrder).where(AdOrder.campaign_id == campaign.id))
    ).all()
    assert orders == []


# ---------------------------------------------------------------------------
# GET /billing/ad-orders?campaign_id=


async def test_list_orders_owner_scoped(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    business = await _seed_business(session)
    campaign = await _seed_campaign(session, business.id)
    created = await client.post(
        "/billing/ad-orders", json={"campaign_id": str(campaign.id)}, headers=_as(OWNER)
    )
    assert created.status_code == 201

    mine = await client.get(f"/billing/ad-orders?campaign_id={campaign.id}", headers=_as(OWNER))
    assert mine.status_code == 200
    body = mine.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == created.json()["id"]
    assert body["items"][0]["status"] == "created"

    foreign = await client.get(
        f"/billing/ad-orders?campaign_id={campaign.id}", headers=_as(STRANGER)
    )
    assert foreign.status_code == 404


async def test_list_orders_unknown_campaign_404(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    response = await client.get(
        f"/billing/ad-orders?campaign_id={uuid.uuid4()}", headers=_as(OWNER)
    )
    assert response.status_code == 404


async def test_list_orders_requires_campaign_id(
    api: tuple[httpx.AsyncClient, AsyncSession, FakeRazorpay],
) -> None:
    client, session, fake = api
    await _enable_billing(session)
    response = await client.get("/billing/ad-orders", headers=_as(OWNER))
    assert response.status_code == 422  # missing required query param
