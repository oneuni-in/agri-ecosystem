"""D21 Task 7: creative approval flows ONLY through the unified moderation
queue - even admin-created creatives (Task 6) start pending and must be
decided via /admin/moderation/creative/{id}/{approve,reject}, never a
bespoke ads route."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.ads.models import Campaign, Creative
from modules.ads.moderation_sources import CreativeSource
from shared.audit import AuditEntry
from shared.db import get_session
from shared.lookups import (
    BusinessRef,
    NotifyContact,
    register_business_resolver,
    register_contact_resolver,
)
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

ADMIN = uuid.uuid4()
KNOWN_BUSINESS = uuid.uuid4()


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, roles: str) -> dict[str, str]:
    return {"x-test-user": str(user_id), "x-test-roles": roles}


async def _biz_resolver(session: AsyncSession, business_id: uuid.UUID) -> BusinessRef | None:
    if business_id == KNOWN_BUSINESS:
        return BusinessRef(id=business_id, owner_user_id=uuid.uuid4(), name="Kovai Mills")
    return None


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()  # create_app registers the real ads sources
    register_business_resolver(_biz_resolver)  # after create_app(): D20 pattern

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
        yield client, db_session


def _campaign_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "advertiser_business_id": str(KNOWN_BUSINESS),
        "name": "Kovai Mills - kharif push",
        "budget_display": "Rs 50,000/mo",
        "flight_start": "2026-08-01",
        "flight_end": "2026-09-01",
    }
    body.update(overrides)
    return body


def _creative_body(campaign_id: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "campaign_id": campaign_id,
        "media_keys": ["ads/creative-1.jpg"],
        "copy": {"en": {"title": "Kharif seeds now live", "body": "Book your order today."}},
        "target_url": "https://kovaimills.example.com/offers",
    }
    body.update(overrides)
    return body


async def _seed_campaign_and_creative(client: httpx.AsyncClient) -> tuple[str, str]:
    r = await client.post(
        "/admin/ads/campaigns", json=_campaign_body(), headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 201, r.text
    campaign_id: str = r.json()["id"]
    r2 = await client.post(
        "/admin/ads/creatives", json=_creative_body(campaign_id), headers=_as(ADMIN, "staff")
    )
    assert r2.status_code == 201, r2.text
    creative_id: str = r2.json()["id"]
    return campaign_id, creative_id


async def test_queue_lists_pending_creative(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    campaign_id, creative_id = await _seed_campaign_and_creative(client)
    r = await client.get("/admin/moderation/queue?type=creative", headers=_as(ADMIN, "staff"))
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["id"] == creative_id
    payload = items[0]["payload"]
    assert payload["campaign_id"] == campaign_id
    assert payload["media_count"] == 1
    assert payload["copy"]["en"]["title"] == "Kharif seeds now live"
    assert payload["target_url"] == "https://kovaimills.example.com/offers"
    assert payload["status"] == "pending"


async def test_creative_approve_via_unified_queue(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    campaign_id, creative_id = await _seed_campaign_and_creative(client)
    r = await client.post(
        f"/admin/moderation/creative/{creative_id}/approve",
        json={"note": "looks good"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200, r.text
    fresh = await session.get(Creative, uuid.UUID(creative_id))
    assert fresh is not None and fresh.moderation_status == "approved"
    entry = await session.scalar(
        select(AuditEntry)
        .where(AuditEntry.action == "ads.creative_approved")
        .order_by(AuditEntry.id.desc())
    )
    assert entry is not None and entry.target_id == creative_id


async def test_creative_reject_via_unified_queue(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    _, creative_id = await _seed_campaign_and_creative(client)
    r = await client.post(
        f"/admin/moderation/creative/{creative_id}/reject",
        json={"note": "bad copy"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200, r.text
    fresh = await session.get(Creative, uuid.UUID(creative_id))
    assert fresh is not None and fresh.moderation_status == "rejected"
    entry = await session.scalar(
        select(AuditEntry)
        .where(AuditEntry.action == "ads.creative_rejected")
        .order_by(AuditEntry.id.desc())
    )
    assert entry is not None and entry.target_id == creative_id


async def test_creative_double_decide_409(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    _, creative_id = await _seed_campaign_and_creative(client)
    first = await client.post(
        f"/admin/moderation/creative/{creative_id}/approve",
        json={},
        headers=_as(ADMIN, "staff"),
    )
    assert first.status_code == 200
    second = await client.post(
        f"/admin/moderation/creative/{creative_id}/reject",
        json={"note": "changed my mind"},
        headers=_as(ADMIN, "staff"),
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "already_decided"


async def test_summary_includes_creative(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    await _seed_campaign_and_creative(client)
    r = await client.get("/admin/moderation/summary", headers=_as(ADMIN, "staff"))
    assert r.status_code == 200
    counts = r.json()["counts"]
    assert counts["creative"] == 1


# ---------------------------------------------------------------------------
# M5 Task 7: approval is the moderation half of the payment-AND-moderation
# activation gate (modules/ads/lifecycle.py::maybe_activate).


async def test_approve_activates_paid_campaign(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    campaign_id, creative_id = await _seed_campaign_and_creative(client)
    campaign = await session.get(Campaign, uuid.UUID(campaign_id))
    assert campaign is not None
    campaign.status = "pending_moderation"
    campaign.paid_at = datetime.now(UTC)
    await session.flush()

    r = await client.post(
        f"/admin/moderation/creative/{creative_id}/approve",
        json={"note": "looks good"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200, r.text

    fresh_creative = await session.get(Creative, uuid.UUID(creative_id))
    assert fresh_creative is not None and fresh_creative.moderation_status == "approved"
    fresh_campaign = await session.get(Campaign, uuid.UUID(campaign_id))
    assert fresh_campaign is not None and fresh_campaign.status == "active"


async def test_approve_does_not_activate_unpaid_campaign(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """THREAT: activation-before-payment. Moderation approval alone, with no
    paid_at, must leave the campaign in pending_moderation."""
    client, session = api
    campaign_id, creative_id = await _seed_campaign_and_creative(client)
    campaign = await session.get(Campaign, uuid.UUID(campaign_id))
    assert campaign is not None
    campaign.status = "pending_moderation"  # paid_at deliberately left None
    await session.flush()

    r = await client.post(
        f"/admin/moderation/creative/{creative_id}/approve",
        json={"note": "looks good"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200, r.text

    fresh_creative = await session.get(Creative, uuid.UUID(creative_id))
    assert fresh_creative is not None and fresh_creative.moderation_status == "approved"
    fresh_campaign = await session.get(Campaign, uuid.UUID(campaign_id))
    assert fresh_campaign is not None and fresh_campaign.status == "pending_moderation"


# ---------------------------------------------------------------------------
# M5 Task 12: creative.rejected must carry a full notify-routable payload
# (not the old bare {creative_id, campaign_id} shape) now that notify's
# EVENT_ROUTES/STREAMS actually consume the "ads" stream. Exercised at the
# CreativeSource level directly (not through the HTTP api fixture) since
# that is the only way to inspect ModDecision.events before ops publishes
# them onto the bus.


async def test_reject_emits_notify_routed_payload(db_session: AsyncSession) -> None:
    owner_id = uuid.uuid4()
    business_id = uuid.uuid4()

    async def _biz(session: AsyncSession, biz_id: uuid.UUID) -> BusinessRef | None:
        if biz_id == business_id:
            return BusinessRef(id=biz_id, owner_user_id=owner_id, name="Kovai Mills")
        return None

    async def _contact(session: AsyncSession, user_id: uuid.UUID) -> NotifyContact | None:
        return NotifyContact(email="owner@example.com", locale="hi")

    register_business_resolver(_biz)
    register_contact_resolver(_contact)

    campaign = Campaign(
        advertiser_business_id=business_id,
        name="Kharif push",
        status="pending_moderation",
        flight_start=date(2026, 8, 1),
        flight_end=date(2026, 9, 1),
    )
    db_session.add(campaign)
    await db_session.flush()
    creative = Creative(
        campaign_id=campaign.id,
        media_keys=["ads/x.jpg"],
        copy={"en": {"title": "t", "body": "b"}},
        target_url="https://example.com",
    )
    db_session.add(creative)
    await db_session.flush()

    decision = await CreativeSource().reject(
        db_session, item_id=creative.id, actor_user_id=ADMIN, note="bad copy", ip=None
    )

    assert len(decision.events) == 1
    event = decision.events[0]
    assert event.stream == "ads"
    assert event.event_type == "creative.rejected"
    assert event.payload["user_id"] == str(owner_id)
    assert event.payload["locale"] == "hi"
    assert event.payload["email"] == "owner@example.com"
    assert event.payload["vars"] == {"campaign_name": "Kharif push"}


async def test_reject_emits_no_event_when_business_unresolvable(
    db_session: AsyncSession,
) -> None:
    """Same "nobody to notify" rule as _activation_event - an unowned/
    unresolvable business means no event, not a crash."""

    async def _biz_none(session: AsyncSession, biz_id: uuid.UUID) -> BusinessRef | None:
        return None

    register_business_resolver(_biz_none)

    campaign = Campaign(
        advertiser_business_id=uuid.uuid4(),
        name="Kharif push",
        status="pending_moderation",
        flight_start=date(2026, 8, 1),
        flight_end=date(2026, 9, 1),
    )
    db_session.add(campaign)
    await db_session.flush()
    creative = Creative(
        campaign_id=campaign.id,
        media_keys=["ads/x.jpg"],
        copy={"en": {"title": "t", "body": "b"}},
        target_url="https://example.com",
    )
    db_session.add(creative)
    await db_session.flush()

    decision = await CreativeSource().reject(
        db_session, item_id=creative.id, actor_user_id=ADMIN, note="bad copy", ip=None
    )

    assert decision.events == ()
