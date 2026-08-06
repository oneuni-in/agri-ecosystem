"""M5 Task 13: advertiser campaign analytics (GET /ads/my/campaigns/{id}/
stats). Two data sources feed this route:

  - ads.impressions/ads.clicks (exact, keyed by placement_id) -> impressions/
    clicks/ctr_bp/by_day.
  - ads.delivery_decisions (campaign_id + pincode/category/tier) -> by_pincode
    /by_category/by_tier. SAMPLED at settings.ads_delivery_log_sample UNLESS
    the campaign is paid (price_paise is not None), in which case
    modules.ads.service.log_delivery's new `always` flag (set by
    modules/ads/router.py::serve) bypasses the sampling gate entirely - that
    is the behaviour `test_priced_campaign_serve_always_bypasses_sampling`
    below proves directly against a live /ads/serve call with sampling
    forced to 0.

spend_paise is DERIVED read-side (no mutable balance column) - see
selfserve_router._spend_paise. NN4 (IDOR: not-yours == not-found) applies
here exactly like every other route in this router."""

import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign, Click, Creative, DeliveryDecision, Impression, Placement
from modules.directory import service as directory_service
from settings import get_settings
from shared.flags import FeatureFlag, reset_flag_cache
from tests.d26_helpers import _as, api  # noqa: F401 (pytest fixture injection)
from tests.test_ads_serve import ads_redis  # noqa: F401 (pytest fixture injection)

pytestmark = pytest.mark.asyncio

OWNER = uuid.uuid4()
STRANGER = uuid.uuid4()
PINCODE = "641001"


async def _enable_ads(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "ads_enabled")
    assert flag is not None
    flag.enabled = True
    await session.flush()
    reset_flag_cache()


async def _business(session: AsyncSession, owner: uuid.UUID = OWNER) -> uuid.UUID:
    business = await directory_service.create_business(
        session,
        owner_user_id=owner,
        name=f"Advertiser {uuid.uuid4().hex[:8]}",
        type_="shop",
        primary_pincode=PINCODE,
    )
    return business.id


async def _seed_campaign(
    session: AsyncSession,
    *,
    owner: uuid.UUID = OWNER,
    price_paise: int | None = None,
    pricing_model: str | None = None,
    budget_serves_total: int | None = None,
    budget_serves_used: int = 0,
    paid_at: datetime | None = None,
    campaign_status: str = "active",
    slot_key: str = "milk_home_hero",
) -> tuple[Campaign, Placement, Creative]:
    """A servable campaign (active + in-flight + approved creative +
    untargeted placement) so the `always`-bypass test can drive it straight
    through /ads/serve; the plain stats-math tests only need the row to
    exist and don't care whether it would actually serve."""
    business_id = await _business(session, owner=owner)
    today = date.today()
    campaign = Campaign(
        advertiser_business_id=business_id,
        name="Stats campaign",
        status=campaign_status,
        flight_start=today - timedelta(days=1),
        flight_end=today + timedelta(days=30),
        pricing_model=pricing_model,
        price_paise=price_paise,
        budget_serves_total=budget_serves_total,
        budget_serves_used=budget_serves_used,
        paid_at=paid_at,
    )
    session.add(campaign)
    await session.flush()
    creative = Creative(
        campaign_id=campaign.id,
        media_keys=["ads/creative-1.jpg"],
        copy={"en": {"title": "Kharif seeds now live", "body": "Book your order today."}},
        target_url="https://kovaimills.example.com/offers",
        moderation_status="approved",
    )
    session.add(creative)
    placement = Placement(campaign_id=campaign.id, slot_key=slot_key, geo_target={}, weight=1)
    session.add(placement)
    await session.flush()
    return campaign, placement, creative


async def test_priced_campaign_serve_always_bypasses_sampling(
    api: tuple[httpx.AsyncClient, AsyncSession],
    ads_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of Task 13's `always` flag: a paid campaign's serves
    are logged to ads.delivery_decisions EVEN WITH sampling forced to 0."""
    monkeypatch.setattr(get_settings(), "ads_delivery_log_sample", 0.0)
    client, session = api
    await _enable_ads(session)
    campaign, placement, _creative = await _seed_campaign(
        session, price_paise=100000, pricing_model="cpm"
    )

    r = await client.get("/ads/serve", params={"slot": placement.slot_key})
    assert r.status_code == 200, r.text
    assert r.json()["ad"] is not None

    count = await session.scalar(
        select(func.count())
        .select_from(DeliveryDecision)
        .where(DeliveryDecision.campaign_id == campaign.id)
    )
    assert count == 1  # sample rate 0 would normally have written zero rows


async def test_house_campaign_serve_still_sampled(
    api: tuple[httpx.AsyncClient, AsyncSession],
    ads_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Control for the test above: an unpriced (house) campaign keeps the
    OLD sampled behaviour - sample rate 0 writes nothing."""
    monkeypatch.setattr(get_settings(), "ads_delivery_log_sample", 0.0)
    client, session = api
    await _enable_ads(session)
    campaign, placement, _creative = await _seed_campaign(session, price_paise=None)

    r = await client.get("/ads/serve", params={"slot": placement.slot_key})
    assert r.status_code == 200, r.text
    assert r.json()["ad"] is not None

    count = await session.scalar(
        select(func.count())
        .select_from(DeliveryDecision)
        .where(DeliveryDecision.campaign_id == campaign.id)
    )
    assert count == 0


async def test_stats_happy_path_counts_ctr_spend_and_breakdowns(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign, placement, creative = await _seed_campaign(
        session,
        price_paise=100000,
        pricing_model="cpm",
        budget_serves_total=10000,
        budget_serves_used=2500,
    )
    now = datetime.now(UTC)
    for _ in range(40):
        session.add(
            Impression(
                placement_id=placement.id,
                creative_id=creative.id,
                slot_key=placement.slot_key,
                viewer_hash="h",
                occurred_at=now,
            )
        )
    for _ in range(5):
        session.add(
            Click(
                placement_id=placement.id,
                creative_id=creative.id,
                slot_key=placement.slot_key,
                viewer_hash="h",
                occurred_at=now,
            )
        )
    for pincode, category, tier in (
        ("641001", "ghee", 2),
        ("641001", "ghee", 2),
        ("600001", "milk", 4),
        (None, None, None),
    ):
        session.add(
            DeliveryDecision(
                campaign_id=campaign.id,
                placement_id=placement.id,
                creative_id=creative.id,
                slot_key=placement.slot_key,
                pincode=pincode,
                category=category,
                why_served="global",
                viewer_hash="h",
                occurred_at=now,
                tier=tier,
            )
        )
    await session.flush()

    resp = await client.get(
        f"/ads/my/campaigns/{campaign.id}/stats", params={"days": 7}, headers=_as(OWNER)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["days"] == 7
    assert body["serves_used"] == 2500
    assert body["serves_total"] == 10000
    assert body["spend_paise"] == 25000  # 100000 * 2500 // 10000
    assert body["impressions"] == 40
    assert body["clicks"] == 5
    assert body["ctr_bp"] == 1250  # 5 * 10000 // 40
    assert body["sampled"] is False

    assert len(body["by_day"]) == 1
    assert body["by_day"][0]["day"] == date.today().isoformat()
    assert body["by_day"][0]["impressions"] == 40
    assert body["by_day"][0]["clicks"] == 5

    assert {row["key"]: row["serves"] for row in body["by_pincode"]} == {
        "641001": 2,
        "600001": 1,
        "unknown": 1,
    }
    assert {row["key"]: row["serves"] for row in body["by_category"]} == {
        "ghee": 2,
        "milk": 1,
        "unknown": 1,
    }
    assert {row["key"]: row["serves"] for row in body["by_tier"]} == {
        "2": 2,
        "4": 1,
        "unknown": 1,
    }


async def test_stats_ctr_and_spend_zero_when_no_activity(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """0-safe division: no impressions -> ctr_bp 0; total unset -> spend 0."""
    client, session = api
    await _enable_ads(session)
    campaign, _placement, _creative = await _seed_campaign(
        session, price_paise=100000, pricing_model="cpm", budget_serves_total=None
    )
    await session.flush()

    resp = await client.get(f"/ads/my/campaigns/{campaign.id}/stats", headers=_as(OWNER))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["impressions"] == 0
    assert body["clicks"] == 0
    assert body["ctr_bp"] == 0
    assert body["spend_paise"] == 0  # unlimited (budget_serves_total None) cpm campaign
    assert body["by_day"] == []
    assert body["by_pincode"] == []


async def test_stats_flat_weekly_spend_paid_vs_unpaid(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    paid, _p1, _c1 = await _seed_campaign(
        session, price_paise=150000, pricing_model="flat_weekly", paid_at=datetime.now(UTC)
    )
    unpaid, _p2, _c2 = await _seed_campaign(
        session, price_paise=150000, pricing_model="flat_weekly", paid_at=None
    )
    await session.flush()

    paid_resp = await client.get(f"/ads/my/campaigns/{paid.id}/stats", headers=_as(OWNER))
    assert paid_resp.status_code == 200, paid_resp.text
    assert paid_resp.json()["spend_paise"] == 150000
    assert paid_resp.json()["sampled"] is False

    unpaid_resp = await client.get(f"/ads/my/campaigns/{unpaid.id}/stats", headers=_as(OWNER))
    assert unpaid_resp.status_code == 200, unpaid_resp.text
    assert unpaid_resp.json()["spend_paise"] == 0


async def test_stats_house_campaign_sampled_true_and_zero_spend(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign, _placement, _creative = await _seed_campaign(
        session, price_paise=None, pricing_model=None
    )
    await session.flush()

    resp = await client.get(f"/ads/my/campaigns/{campaign.id}/stats", headers=_as(OWNER))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sampled"] is True
    assert body["spend_paise"] == 0


async def test_stats_foreign_campaign_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign, _placement, _creative = await _seed_campaign(session, owner=OWNER)
    await session.flush()

    resp = await client.get(f"/ads/my/campaigns/{campaign.id}/stats", headers=_as(STRANGER))
    assert resp.status_code == 404

    own = await client.get(f"/ads/my/campaigns/{campaign.id}/stats", headers=_as(OWNER))
    assert own.status_code == 200

    missing = await client.get(f"/ads/my/campaigns/{uuid.uuid4()}/stats", headers=_as(OWNER))
    assert missing.status_code == 404


async def test_stats_flag_off_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _session = api
    resp = await client.get(f"/ads/my/campaigns/{uuid.uuid4()}/stats", headers=_as(OWNER))
    assert resp.status_code == 404


async def test_stats_days_validation_422(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign, _placement, _creative = await _seed_campaign(session, owner=OWNER)
    await session.flush()

    bad = await client.get(
        f"/ads/my/campaigns/{campaign.id}/stats", params={"days": 5}, headers=_as(OWNER)
    )
    assert bad.status_code == 422

    for days in (7, 30, 90):
        ok = await client.get(
            f"/ads/my/campaigns/{campaign.id}/stats", params={"days": days}, headers=_as(OWNER)
        )
        assert ok.status_code == 200, (days, ok.text)
        assert ok.json()["days"] == days
