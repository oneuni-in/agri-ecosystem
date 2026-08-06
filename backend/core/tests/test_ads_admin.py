"""modules/ads admin CRUD (D21): campaigns, creatives, placements.

Creatives always land `pending` - approval is the unified moderation queue's
job (Task 7), never this router. No events publish here (ads CRUD is
silent)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.ads.models import Campaign, Click, Creative, Impression
from shared.audit import AuditEntry
from shared.db import get_session
from shared.lookups import BusinessRef, register_business_resolver
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

ADMIN = uuid.uuid4()
KNOWN_BUSINESS = uuid.uuid4()
UNKNOWN_BUSINESS = uuid.uuid4()


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
async def api(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
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
        yield client


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


async def _create_campaign(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/admin/ads/campaigns", json=_campaign_body(), headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 201, r.text
    campaign_id: str = r.json()["id"]
    return campaign_id


def _creative_body(campaign_id: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "campaign_id": campaign_id,
        "media_keys": ["ads/creative-1.jpg"],
        "copy": {"en": {"title": "Kharif seeds now live", "body": "Book your order today."}},
        "target_url": "https://kovaimills.example.com/offers",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# 403 non-staff


async def test_non_staff_403(api: httpx.AsyncClient) -> None:
    r = await api.post("/admin/ads/campaigns", json=_campaign_body(), headers=_as(ADMIN, "user"))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# campaigns


async def test_campaign_create_happy(api: httpx.AsyncClient) -> None:
    r = await api.post("/admin/ads/campaigns", json=_campaign_body(), headers=_as(ADMIN, "staff"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["advertiser_business_id"] == str(KNOWN_BUSINESS)
    assert uuid.UUID(body["id"])


async def test_campaign_budget_roundtrip(api: httpx.AsyncClient) -> None:
    """M3: serve-credit budget is settable at create; used starts at 0;
    omitting it means unlimited (NULL)."""
    r = await api.post(
        "/admin/ads/campaigns",
        json=_campaign_body(budget_serves_total=100),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["budget_serves_total"] == 100
    assert body["budget_serves_used"] == 0

    r2 = await api.post("/admin/ads/campaigns", json=_campaign_body(), headers=_as(ADMIN, "staff"))
    assert r2.json()["budget_serves_total"] is None


async def test_campaign_budget_negative_422(api: httpx.AsyncClient) -> None:
    r = await api.post(
        "/admin/ads/campaigns",
        json=_campaign_body(budget_serves_total=-5),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422


async def test_campaign_create_unknown_business_422(api: httpx.AsyncClient) -> None:
    r = await api.post(
        "/admin/ads/campaigns",
        json=_campaign_body(advertiser_business_id=str(UNKNOWN_BUSINESS)),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "unknown_business"


async def test_campaign_status_flip(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        f"/admin/ads/campaigns/{campaign_id}/status",
        json={"status": "active"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"


async def test_admin_cannot_activate_unpaid_or_unapproved_priced_campaign(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """M5 Task 7 (decision 14): the payment-AND-moderation activation gate
    applies to staff-driven transitions too, not just self-serve's own
    routes - a priced campaign that hasn't paid, or hasn't cleared
    moderation, must never be force-activated. Payment is checked first
    (payment_required); once paid, moderation is checked
    (moderation_required)."""
    campaign_id = await _create_campaign(api)
    db_campaign = await db_session.get(Campaign, uuid.UUID(campaign_id))
    assert db_campaign is not None
    db_campaign.price_paise = 50_000
    await db_session.flush()

    r = await api.post(
        f"/admin/ads/campaigns/{campaign_id}/status",
        json={"status": "active"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "payment_required"

    # paying it off clears the payment half of the gate, but there is still
    # no approved creative
    db_campaign.paid_at = datetime.now(UTC)
    await db_session.flush()
    r2 = await api.post(
        f"/admin/ads/campaigns/{campaign_id}/status",
        json={"status": "active"},
        headers=_as(ADMIN, "staff"),
    )
    assert r2.status_code == 422
    assert r2.json()["detail"] == "moderation_required"

    # approving a creative clears the moderation half too
    creative = Creative(
        campaign_id=db_campaign.id,
        media_keys=[],
        copy={"en": {"title": "t", "body": "b"}},
        target_url="https://example.com",
    )
    db_session.add(creative)
    await db_session.flush()
    creative.moderation_status = "approved"
    await db_session.flush()

    r3 = await api.post(
        f"/admin/ads/campaigns/{campaign_id}/status",
        json={"status": "active"},
        headers=_as(ADMIN, "staff"),
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "active"


async def test_admin_cannot_push_paid_campaign_back_to_draft(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """MONEY (M5 review): `draft` is still in the admin-settable
    CampaignStatus literal, which predates the 8-state self-serve lifecycle.
    Sending a PAID campaign back to draft hands it to the advertiser's
    draft-only PATCH, which re-quotes at today's rate card and rewrites
    price/budget - while an AdOrder, a ledger row and an already-emailed GST
    invoice all still say the old number. (No double charge - the partial
    unique index blocks that - but the campaign and the money on record
    silently diverge.)"""
    campaign_id = await _create_campaign(api)
    db_campaign = await db_session.get(Campaign, uuid.UUID(campaign_id))
    assert db_campaign is not None
    db_campaign.price_paise = 118_000
    db_campaign.paid_at = datetime.now(UTC)
    db_campaign.status = "active"
    await db_session.flush()

    r = await api.post(
        f"/admin/ads/campaigns/{campaign_id}/status",
        json={"status": "draft"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "not_allowed_for_paid_campaign"
    await db_session.refresh(db_campaign)
    assert db_campaign.status == "active"  # untouched

    # pausing/archiving a paid campaign stays available to staff
    paused = await api.post(
        f"/admin/ads/campaigns/{campaign_id}/status",
        json={"status": "paused"},
        headers=_as(ADMIN, "staff"),
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"


async def test_admin_can_still_draft_an_unpriced_house_campaign(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """price_paise IS NULL (house/admin campaign, never billed, no order and
    no invoice to desync from) keeps today's unrestricted behaviour."""
    campaign_id = await _create_campaign(api)
    db_campaign = await db_session.get(Campaign, uuid.UUID(campaign_id))
    assert db_campaign is not None
    db_campaign.status = "active"
    await db_session.flush()

    r = await api.post(
        f"/admin/ads/campaigns/{campaign_id}/status",
        json={"status": "draft"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft"


async def test_campaign_out_exposes_price_and_paid_at(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """Staff had no way to tell a paid self-serve campaign from a house one
    in the admin listing - which is exactly the distinction the paid-campaign
    status guard turns on."""
    campaign_id = await _create_campaign(api)
    house = await api.get("/admin/ads/campaigns", headers=_as(ADMIN, "staff"))
    assert house.status_code == 200
    row = next(c for c in house.json()["items"] if c["id"] == campaign_id)
    assert row["price_paise"] is None and row["paid_at"] is None

    db_campaign = await db_session.get(Campaign, uuid.UUID(campaign_id))
    assert db_campaign is not None
    db_campaign.price_paise = 118_000
    db_campaign.paid_at = datetime.now(UTC)
    await db_session.flush()

    paid = await api.get("/admin/ads/campaigns", headers=_as(ADMIN, "staff"))
    paid_row = next(c for c in paid.json()["items"] if c["id"] == campaign_id)
    assert paid_row["price_paise"] == 118_000
    assert paid_row["paid_at"] is not None


async def test_admin_activates_unpriced_house_campaign_freely(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """price_paise IS NULL (house/admin campaign, never billed) is exempt
    from the payment gate - "unpaid" is meaningless for it."""
    campaign_id = await _create_campaign(api)
    r = await api.post(
        f"/admin/ads/campaigns/{campaign_id}/status",
        json={"status": "active"},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"


async def test_campaign_out_serializes_pending_payment_status(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """Reconciliation: CampaignStatus (schemas.py) still lists the 4
    admin-settable values only, but the DB CHECK now has 8 - CampaignOut.status
    must serialize any of them (it is a plain str, not the Literal) so the
    admin listing doesn't choke on a self-serve lifecycle status."""
    campaign_id = await _create_campaign(api)
    db_campaign = await db_session.get(Campaign, uuid.UUID(campaign_id))
    assert db_campaign is not None
    db_campaign.status = "pending_payment"
    await db_session.flush()

    r = await api.get("/admin/ads/campaigns", headers=_as(ADMIN, "staff"))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(item["id"] == campaign_id and item["status"] == "pending_payment" for item in items)


async def test_campaign_list_cursor_pagination(api: httpx.AsyncClient) -> None:
    for _ in range(3):
        await _create_campaign(api)
    r1 = await api.get("/admin/ads/campaigns?limit=2", headers=_as(ADMIN, "staff"))
    assert r1.status_code == 200
    page1 = r1.json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None

    r2 = await api.get(
        f"/admin/ads/campaigns?limit=2&cursor={page1['next_cursor']}",
        headers=_as(ADMIN, "staff"),
    )
    assert r2.status_code == 200
    page2 = r2.json()
    assert len(page2["items"]) == 1
    seen_ids = {item["id"] for item in page1["items"]} | {item["id"] for item in page2["items"]}
    assert len(seen_ids) == 3


# ---------------------------------------------------------------------------
# creatives


async def test_creative_created_pending(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/creatives", json=_creative_body(campaign_id), headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["moderation_status"] == "pending"
    assert body["copy"]["en"]["title"] == "Kharif seeds now live"


async def test_creative_target_url_javascript_scheme_422(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/creatives",
        json=_creative_body(campaign_id, target_url="javascript:alert(1)"),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422


async def test_creative_target_url_data_scheme_422(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/creatives",
        json=_creative_body(campaign_id, target_url="data:text/html,<script>1</script>"),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422


async def test_creative_copy_missing_en_422(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/creatives",
        json=_creative_body(
            campaign_id, copy={"ta": {"title": "Only Tamil", "body": "No English"}}
        ),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422


async def test_creative_unknown_campaign_422(api: httpx.AsyncClient) -> None:
    r = await api.post(
        "/admin/ads/creatives",
        json=_creative_body(str(uuid.uuid4())),
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "unknown_campaign"


async def test_creative_list_filters_by_campaign(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    other_campaign_id = await _create_campaign(api)
    await api.post(
        "/admin/ads/creatives", json=_creative_body(campaign_id), headers=_as(ADMIN, "staff")
    )
    await api.post(
        "/admin/ads/creatives",
        json=_creative_body(other_campaign_id),
        headers=_as(ADMIN, "staff"),
    )
    r = await api.get(
        f"/admin/ads/creatives?campaign_id={campaign_id}", headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["campaign_id"] == campaign_id


async def test_creative_media_unknown_creative_404(api: httpx.AsyncClient) -> None:
    r = await api.get(f"/admin/ads/creatives/{uuid.uuid4()}/media/0", headers=_as(ADMIN, "staff"))
    assert r.status_code == 404


async def test_creative_media_index_out_of_range_404(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/creatives",
        json=_creative_body(campaign_id, media_keys=[]),
        headers=_as(ADMIN, "staff"),
    )
    creative_id = r.json()["id"]
    r2 = await api.get(f"/admin/ads/creatives/{creative_id}/media/0", headers=_as(ADMIN, "staff"))
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# placements


async def test_placement_unknown_slot_422(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/placements",
        json={"campaign_id": campaign_id, "slot_key": "homepage_hero", "weight": 1},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "unknown_slot_key"


async def test_placement_unknown_campaign_422(api: httpx.AsyncClient) -> None:
    r = await api.post(
        "/admin/ads/placements",
        json={
            "campaign_id": str(uuid.uuid4()),
            "slot_key": "directory_browse",
            "weight": 1,
        },
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "unknown_campaign"


async def test_placement_geo_target_unknown_key_422(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/placements",
        json={
            "campaign_id": campaign_id,
            "slot_key": "directory_browse",
            "geo_target": {"village": "x"},
            "weight": 1,
        },
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422


async def test_placement_categories_accepted_and_bad_shape_422(api: httpx.AsyncClient) -> None:
    """M2: category-targetable inventory - values are shape-validated only
    (matched at serve time against the M1 schema `category` strings)."""
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/placements",
        json={
            "campaign_id": campaign_id,
            "slot_key": "milk_category_banner",
            "geo_target": {"categories": ["ghee", "milk-powder"]},
            "weight": 1,
        },
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["geo_target"] == {"categories": ["ghee", "milk-powder"]}

    bad = await api.post(
        "/admin/ads/placements",
        json={
            "campaign_id": campaign_id,
            "slot_key": "milk_category_banner",
            "geo_target": {"categories": ["Bad Value!"]},
            "weight": 1,
        },
        headers=_as(ADMIN, "staff"),
    )
    assert bad.status_code == 422


async def test_placement_create_and_status_flip(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/placements",
        json={
            "campaign_id": campaign_id,
            "slot_key": "directory_browse",
            "geo_target": {"state": 33},
            "weight": 2,
        },
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "active"
    assert body["geo_target"] == {"state": 33}
    placement_id = body["id"]

    r2 = await api.post(
        f"/admin/ads/placements/{placement_id}/status",
        json={"status": "paused"},
        headers=_as(ADMIN, "staff"),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "paused"


async def test_placement_list_filters_by_slot_key(api: httpx.AsyncClient) -> None:
    campaign_id = await _create_campaign(api)
    await api.post(
        "/admin/ads/placements",
        json={"campaign_id": campaign_id, "slot_key": "directory_browse", "weight": 1},
        headers=_as(ADMIN, "staff"),
    )
    r = await api.get(
        "/admin/ads/placements?slot_key=directory_browse", headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["slot_key"] == "directory_browse"


async def _create_placement(api: httpx.AsyncClient) -> str:
    campaign_id = await _create_campaign(api)
    r = await api.post(
        "/admin/ads/placements",
        json={"campaign_id": campaign_id, "slot_key": "directory_browse", "weight": 1},
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 201, r.text
    placement_id: str = r.json()["id"]
    return placement_id


# ---------------------------------------------------------------------------
# stats


async def test_stats_happy(api: httpx.AsyncClient, db_session: AsyncSession) -> None:
    placement_id_str = await _create_placement(api)
    placement_id = uuid.UUID(placement_id_str)
    creative_id = uuid.uuid4()

    today = date.today()
    tomorrow = today + timedelta(days=1)

    # Seed impressions at today and tomorrow
    today_midnight = datetime.combine(today, time(0), tzinfo=UTC)
    tomorrow_midnight = datetime.combine(tomorrow, time(0), tzinfo=UTC)

    for _ in range(5):
        db_session.add(
            Impression(
                placement_id=placement_id,
                creative_id=creative_id,
                slot_key="directory_browse",
                viewer_hash="hash1",
                pincode=None,
                occurred_at=today_midnight + timedelta(hours=2),
            )
        )
    for _ in range(3):
        db_session.add(
            Impression(
                placement_id=placement_id,
                creative_id=creative_id,
                slot_key="directory_browse",
                viewer_hash="hash2",
                pincode=None,
                occurred_at=tomorrow_midnight + timedelta(hours=3),
            )
        )

    # Seed clicks at today and tomorrow
    for _ in range(2):
        db_session.add(
            Click(
                placement_id=placement_id,
                creative_id=creative_id,
                slot_key="directory_browse",
                viewer_hash="hash1",
                pincode=None,
                occurred_at=today_midnight + timedelta(hours=2, minutes=30),
            )
        )
    for _ in range(1):
        db_session.add(
            Click(
                placement_id=placement_id,
                creative_id=creative_id,
                slot_key="directory_browse",
                viewer_hash="hash2",
                pincode=None,
                occurred_at=tomorrow_midnight + timedelta(hours=4),
            )
        )
    await db_session.commit()

    r = await api.get(
        f"/admin/ads/stats?placement_id={placement_id_str}&date_from={today}&date_to={tomorrow}",
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["rows"]) == 2
    assert body["rows"][0]["day"] == str(today)
    assert body["rows"][0]["impressions"] == 5
    assert body["rows"][0]["clicks"] == 2
    assert body["rows"][1]["day"] == str(tomorrow)
    assert body["rows"][1]["impressions"] == 3
    assert body["rows"][1]["clicks"] == 1


async def test_stats_range_too_wide_422(api: httpx.AsyncClient) -> None:
    placement_id_str = await _create_placement(api)
    today = date.today()
    date_from = today
    date_to = date_from + timedelta(days=91)

    r = await api.get(
        f"/admin/ads/stats?placement_id={placement_id_str}&date_from={date_from}&date_to={date_to}",
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_range"


async def test_stats_date_to_before_date_from_422(api: httpx.AsyncClient) -> None:
    placement_id_str = await _create_placement(api)
    today = date.today()
    date_from = today
    date_to = today - timedelta(days=1)

    r = await api.get(
        f"/admin/ads/stats?placement_id={placement_id_str}&date_from={date_from}&date_to={date_to}",
        headers=_as(ADMIN, "staff"),
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_range"


async def test_stats_non_staff_403(api: httpx.AsyncClient) -> None:
    placement_id_str = await _create_placement(api)
    today = date.today()

    r = await api.get(
        f"/admin/ads/stats?placement_id={placement_id_str}&date_from={today}&date_to={today}",
        headers=_as(ADMIN, "user"),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# rate card (M5 Task 3)


def _rate_card_config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "cpm_paise": {"1": 31000, "2": 21000, "3": 13000, "4": 9000, "5": 6000},
        "flat_weekly_paise": {"1": 155000, "2": 105000, "3": 65000, "4": 45000, "5": 30000},
        "category_multipliers_bp": {"ghee": 12000, "paneer": 11000},
        "min_total_paise": 12000,
    }
    config.update(overrides)
    return config


async def test_rate_card_get_returns_seeded_v1(api: httpx.AsyncClient) -> None:
    r = await api.get("/admin/ads/rate-card", headers=_as(ADMIN, "staff"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 1
    assert set(body["config"]) == {
        "cpm_paise",
        "flat_weekly_paise",
        "category_multipliers_bp",
        "min_total_paise",
    }


async def test_rate_card_post_creates_v2_and_get_returns_it(api: httpx.AsyncClient) -> None:
    config = _rate_card_config()
    r = await api.post("/admin/ads/rate-card", json={"config": config}, headers=_as(ADMIN, "staff"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 2
    assert body["config"] == config

    r2 = await api.get("/admin/ads/rate-card", headers=_as(ADMIN, "staff"))
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["version"] == 2
    assert body2["config"] == config


async def test_rate_card_post_bad_config_422(api: httpx.AsyncClient) -> None:
    config = _rate_card_config()
    del config["min_total_paise"]
    r = await api.post("/admin/ads/rate-card", json={"config": config}, headers=_as(ADMIN, "staff"))
    assert r.status_code == 422
    assert r.json()["detail"] == "missing_key"


async def test_rate_card_post_requires_staff_403(api: httpx.AsyncClient) -> None:
    r = await api.post(
        "/admin/ads/rate-card",
        json={"config": _rate_card_config()},
        headers=_as(ADMIN, "user"),
    )
    assert r.status_code == 403


async def test_rate_card_post_audited(api: httpx.AsyncClient, db_session: AsyncSession) -> None:
    r = await api.post(
        "/admin/ads/rate-card", json={"config": _rate_card_config()}, headers=_as(ADMIN, "staff")
    )
    assert r.status_code == 201, r.text
    version = r.json()["version"]

    entry = await db_session.scalar(
        select(AuditEntry).where(AuditEntry.action == "ads.rate_card_published")
    )
    assert entry is not None
    assert entry.actor_user_id == ADMIN
    assert entry.target_type == "rate_card"
    assert entry.target_id == str(version)
    assert entry.meta == {"version": version}
