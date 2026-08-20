""" "Live on agri.in" activity feed engine (A-U4b O11, row AG-A69).

The privacy contract is the SCHEMA: directory.activity has no user id, no
person's name, no pincode and no contact column, so the tests here pin (1)
each write hook records the right coarse facts and nothing more, (2)
UNIQUE(kind, source_id) idempotency, (3) the flag-gated public feed route,
and (4) the shape tripwire - a feed item is EXACTLY seven fields.

Scaffold mirrors test_needs_router.py / test_reviews_moderation.py (client
fixture + x-test-user/x-test-roles principal resolver, publish monkeypatched
where a router publishes)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import needs_service, service
from modules.directory.activity import record_activity
from modules.directory.models import Activity, Business, BusinessCoverage, Claim, Verification
from modules.directory.reviews_models import Review
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

PINCODE = "641001"  # geocoded by tn_geo_sample (Coimbatore / Tamil Nadu)

NEED_PAYLOAD: dict[str, Any] = {
    "qty_liters": "1",
    "milk_type": "cow",
    "schedule": "daily",
    "delivery_time": "morning",
}

# The privacy tripwire: a feed item is EXACTLY these seven fields, ever.
FEED_ITEM_FIELDS = {
    "kind",
    "occurred_at",
    "district",
    "state",
    "business_name",
    "business_slug",
    "rating",
}


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str = "user") -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, Any]]]:
    events: list[tuple[str, str, dict[str, Any]]] = []

    async def _fake_publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
        events.append((stream, event_type, payload))
        return "1-1"

    for module in (
        "modules.directory.needs_router",
        "modules.directory.leads_router",
        "modules.directory.admin_router",
        "modules.directory.reviews_admin_router",
        "modules.directory.router",
    ):
        monkeypatch.setattr(f"{module}.publish", _fake_publish)
    return events


@pytest.fixture
def no_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass the Redis daily need cap (test_needs_router.py precedent)."""

    async def _allow(user_id: uuid.UUID, *, now: datetime) -> None:
        return None

    monkeypatch.setattr(needs_service, "claim_need_slot", _allow)


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        if not header:
            return None
        roles = tuple((request.headers.get("x-test-roles") or "user").split(","))
        return _Principal(uuid.UUID(header), roles)

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as http:
        yield http


async def _enable_feed(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "agri_live_feed")
    assert flag is not None  # seeded OFF by 0037
    flag.enabled = True
    await session.flush()
    reset_flag_cache()


async def _covering_vendor(
    session: AsyncSession, *, owner: uuid.UUID | None, name: str = "Sri Valli Dairy"
) -> Business:
    if owner is None:
        business = Business(
            owner_user_id=None,
            name=name,
            slug=f"seeded-{uuid.uuid4().hex[:10]}",
            type="vendor",
            primary_pincode=PINCODE,
        )
        session.add(business)
        await session.flush()
        await session.refresh(business)
    else:
        business = await service.create_business(
            session, owner_user_id=owner, name=name, type_="vendor", primary_pincode=PINCODE
        )
    session.add(BusinessCoverage(business_id=business.id, pincode=PINCODE))
    await session.flush()
    return business


async def _activity_rows(session: AsyncSession, kind: str) -> list[Activity]:
    return list(await session.scalars(select(Activity).where(Activity.kind == kind)))


# ── (a) need_posted: parent id, resolved district, NO pincode anywhere ───


async def test_need_posted_records_district_and_never_the_pincode(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tn_geo_sample: None,
    published: list[tuple[str, str, dict[str, Any]]],
    no_cap: None,
) -> None:
    await _covering_vendor(db_session, owner=uuid.uuid4())
    response = await client.post(
        "/leads/needs",
        json={"pincode": PINCODE, "payload": NEED_PAYLOAD},
        headers=_as(uuid.uuid4()),
    )
    assert response.status_code == 201

    rows = await _activity_rows(db_session, "need_posted")
    assert len(rows) == 1  # one row for the PARENT need, not per child inquiry
    row = rows[0]
    assert row.source_id == uuid.UUID(response.json()["id"])
    assert row.district == "Coimbatore"
    assert row.state == "Tamil Nadu"
    assert row.business_name is None and row.business_slug is None and row.rating is None
    # the pincode was resolved and DROPPED - it appears in NO stored field
    stored = [row.kind, row.district, row.state, row.business_name, row.business_slug]
    assert all(PINCODE not in value for value in stored if value is not None)


# ── (b) unknown pincode -> NULL location, row still recorded ─────────────


async def test_need_posted_unknown_pincode_records_row_with_null_location(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tn_geo_sample: None,
    published: list[tuple[str, str, dict[str, Any]]],
    no_cap: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate a non-TN pincode at the hook's geo lookup (until D65 the geo
    # table is TN-only): the routing still finds coverage, the feed row must
    # arrive with location omitted - NEVER the pincode as a fallback.
    async def _unknown(session: AsyncSession, pincode: str) -> None:
        return None

    monkeypatch.setattr("modules.directory.activity.district_for_pincode", _unknown)
    await _covering_vendor(db_session, owner=uuid.uuid4())
    response = await client.post(
        "/leads/needs",
        json={"pincode": PINCODE, "payload": NEED_PAYLOAD},
        headers=_as(uuid.uuid4()),
    )
    assert response.status_code == 201

    rows = await _activity_rows(db_session, "need_posted")
    assert len(rows) == 1
    assert rows[0].district is None
    assert rows[0].state is None


# ── (c) review_approved: rating + business fields only when public ───────


async def test_review_approved_carries_business_only_when_active(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    business = await service.create_business(
        db_session,
        owner_user_id=uuid.uuid4(),
        name="Agri Shop",
        type_="shop",
        primary_pincode=PINCODE,
    )
    review = Review(
        author_user_id=uuid.uuid4(), target_type="business", target_id=business.id, rating=4
    )
    db_session.add(review)
    await db_session.flush()

    response = await client.post(
        f"/admin/reviews/{review.id}/approve", headers=_as(uuid.uuid4(), "staff")
    )
    assert response.status_code == 200

    rows = await _activity_rows(db_session, "review_approved")
    assert len(rows) == 1
    assert rows[0].source_id == review.id
    assert rows[0].rating == 4
    assert rows[0].business_name == "Agri Shop"
    assert rows[0].business_slug == business.slug


async def test_review_approved_omits_business_when_not_public(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    business = await service.create_business(
        db_session,
        owner_user_id=uuid.uuid4(),
        name="Suspended Shop",
        type_="shop",
        primary_pincode=PINCODE,
    )
    business.status = "suspended"  # not publicly visible (search_sync rule)
    review = Review(
        author_user_id=uuid.uuid4(), target_type="business", target_id=business.id, rating=2
    )
    db_session.add(review)
    await db_session.flush()

    response = await client.post(
        f"/admin/reviews/{review.id}/approve", headers=_as(uuid.uuid4(), "staff")
    )
    assert response.status_code == 200

    rows = await _activity_rows(db_session, "review_approved")
    assert len(rows) == 1
    assert rows[0].rating == 2
    assert rows[0].business_name is None
    assert rows[0].business_slug is None


# ── (d) claim approve + verification approve -> ONE business_joined ──────


async def test_claim_then_verification_approve_is_one_joined_row(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    business = await _covering_vendor(db_session, owner=None, name="Seeded Farm")
    claim = Claim(business_id=business.id, claimant_user_id=uuid.uuid4())
    db_session.add(claim)
    await db_session.flush()

    approve = await client.post(
        f"/admin/directory/claims/{claim.id}/approve",
        json={"note": None},
        headers=_as(uuid.uuid4(), "staff"),
    )
    assert approve.status_code == 200

    verification = Verification(business_id=business.id, method="document", status="pending")
    db_session.add(verification)
    await db_session.flush()
    verify = await client.post(
        f"/admin/directory/verifications/{verification.id}/approve",
        json={"note": None},
        headers=_as(uuid.uuid4(), "staff"),
    )
    assert verify.status_code == 200  # domain write survives the duplicate insert (h)

    rows = await _activity_rows(db_session, "business_joined")
    assert len(rows) == 1  # UNIQUE(kind, source_id): one 'joined' row per business, EVER
    assert rows[0].source_id == business.id
    assert rows[0].business_name == "Seeded Farm"
    assert rows[0].business_slug == business.slug


# ── (e) lead -> lead_sent, nothing about the sender ──────────────────────


async def test_guest_lead_records_lead_sent(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tn_geo_sample: None,
    published: list[tuple[str, str, dict[str, Any]]],
) -> None:
    business = await _covering_vendor(db_session, owner=uuid.uuid4())
    response = await client.post(  # guest: no auth header on purpose
        "/leads/inquiries",
        json={
            "type": "contact",
            "pincode": PINCODE,
            "business_id": str(business.id),
            "payload": {"message": "Do you deliver on Sundays?"},
        },
    )
    assert response.status_code == 201

    rows = await _activity_rows(db_session, "lead_sent")
    assert len(rows) == 1
    assert rows[0].source_id == uuid.UUID(response.json()["id"])
    assert rows[0].business_name == business.name
    assert rows[0].business_slug == business.slug
    assert rows[0].district is None and rows[0].state is None and rows[0].rating is None


# ── (f) the feed route: flag off -> 404; on -> newest-first window ───────


async def test_feed_404s_while_flag_off(client: httpx.AsyncClient) -> None:
    response = await client.get("/directory/feed/live")
    assert response.status_code == 404
    assert response.json()["detail"] == "feature_disabled"


async def test_feed_serves_newest_first_within_window(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _enable_feed(db_session)
    now = datetime.now(UTC)
    for kind, source, delta in (
        ("need_posted", uuid.uuid4(), timedelta(hours=1)),
        ("business_joined", uuid.uuid4(), timedelta(minutes=5)),
        ("lead_sent", uuid.uuid4(), timedelta(hours=25)),  # outside the 24h window
    ):
        await record_activity(db_session, kind=kind, source_id=source, occurred_at=now - delta)

    response = await client.get("/directory/feed/live")
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["kind"] for item in items] == ["business_joined", "need_posted"]


# ── (g) the SHAPE tripwire: exactly seven fields, ever ───────────────────


async def test_feed_item_shape_is_exactly_the_seven_public_fields(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _enable_feed(db_session)
    await record_activity(
        db_session,
        kind="review_approved",
        source_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
        district="Coimbatore",
        state="Tamil Nadu",
        business_name="Agri Shop",
        business_slug="agri-shop",
        rating=5,
    )
    response = await client.get("/directory/feed/live")
    assert response.status_code == 200
    (item,) = response.json()["items"]
    assert set(item.keys()) == FEED_ITEM_FIELDS  # no id, no user, no pincode - EVER


# ── (h) duplicates/failures never break the caller ───────────────────────


async def test_duplicate_record_is_a_noop_and_session_stays_usable(
    db_session: AsyncSession,
) -> None:
    source = uuid.uuid4()
    now = datetime.now(UTC)
    await record_activity(db_session, kind="need_posted", source_id=source, occurred_at=now)
    await record_activity(  # same (kind, source_id): DB-proven no-op
        db_session, kind="need_posted", source_id=source, occurred_at=now, district="Salem"
    )
    rows = await _activity_rows(db_session, "need_posted")
    assert len(rows) == 1
    assert rows[0].district is None  # first write won; the replay changed nothing

    # the caller's transaction was not poisoned: further writes still flush
    await record_activity(db_session, kind="lead_sent", source_id=uuid.uuid4(), occurred_at=now)
    assert len(await _activity_rows(db_session, "lead_sent")) == 1


async def test_record_failure_is_swallowed(db_session: AsyncSession) -> None:
    # rating=99 violates the 1-5 CHECK -> IntegrityError inside the savepoint;
    # record_activity must swallow it and leave the session usable.
    await record_activity(
        db_session,
        kind="review_approved",
        source_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
        rating=99,
    )
    assert await _activity_rows(db_session, "review_approved") == []
    await record_activity(
        db_session, kind="need_posted", source_id=uuid.uuid4(), occurred_at=datetime.now(UTC)
    )
    assert len(await _activity_rows(db_session, "need_posted")) == 1
