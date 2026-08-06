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
selfserve_router._spend_paise - then LEDGER-CAPPED: reviewer-flagged
correctness bug fast-follow. A refund overwrites `budget_serves_total :=
budget_serves_used` (Task 7/10's serve-exhaustion trick, not a real
budget), which made the derived cpm estimate collapse to 100% of price
forever on a refunded campaign. `shared.lookups.resolve_campaign_charged`
(billing's append-only ledger, wired for real by `main.create_app` - the
`api` fixture below uses the real app, so these tests exercise the actual
production resolver, not a stub) is now the ceiling: `spend_paise =
min(derived, charged_net_paise)` whenever the resolver answers a number.
See `test_stats_full_refund_caps_spend_at_zero_despite_budget_bug` for the
literal regression case reviewers reported, and
`test_stats_unregistered_charged_resolver_falls_back_to_derived` for the
fail-closed side.

NN4 (IDOR: not-yours == not-found) applies here exactly like every other
route in this router."""

import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import modules.ads.selfserve_router as selfserve_router_module
from modules.ads.models import Campaign, Click, Creative, DeliveryDecision, Impression, Placement
from modules.billing.models import BillingLedgerEntry
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


def _ledger_entry(campaign: Campaign, *, entry_type: str, amount_paise: int) -> BillingLedgerEntry:
    """order_id=None deliberately: it's nullable (billing.ledger_entries.
    order_id FK) and the partial-unique "one charge per order" index only
    fires on a non-NULL order_id, so this skips seeding a real AdOrder row
    entirely - the cheapest way to get a real ledger row for
    campaign_charged_paise's SUM to read."""
    return BillingLedgerEntry(
        entry_type=entry_type,
        amount_paise=amount_paise,
        order_id=None,
        campaign_id=campaign.id,
        business_id=campaign.advertiser_business_id,
        razorpay_payment_id=f"pay_{campaign.id.hex[:8]}",
        meta={},
    )


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
    assert body["charged_net_paise"] is None  # no billing ledger rows seeded in this test

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
    assert body["charged_net_paise"] is None
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
    assert body["charged_net_paise"] is None  # never charged - house campaign


async def test_stats_full_refund_caps_spend_at_zero_despite_budget_bug(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The reported regression: after a refund's serve-exhaustion trick sets
    budget_serves_total := budget_serves_used, the OLD derived-only
    `price * used // total` collapses to 100% of price - price_paise itself
    - forever. The ledger (charge + full offsetting refund, net 0) must cap
    spend_paise at 0 instead. Uses the REAL registered resolver
    (`api`'s app is `main.create_app()`), not a stub."""
    client, session = api
    await _enable_ads(session)
    campaign, _placement, _creative = await _seed_campaign(
        session,
        price_paise=118000,
        pricing_model="cpm",
        budget_serves_total=5000,
        budget_serves_used=5000,  # refund's exhaustion trick: total pinned to used
    )
    session.add(_ledger_entry(campaign, entry_type="ad_charge", amount_paise=118000))
    session.add(_ledger_entry(campaign, entry_type="ad_refund", amount_paise=-118000))
    await session.flush()

    resp = await client.get(f"/ads/my/campaigns/{campaign.id}/stats", headers=_as(OWNER))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["serves_used"] == body["serves_total"] == 5000  # the bug's precondition
    assert body["charged_net_paise"] == 0
    assert body["spend_paise"] == 0  # NOT 118000 (the derived-only bug)


async def test_stats_partial_refund_caps_spend_at_ledger_net(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """A goodwill partial refund doesn't touch budget_serves_total (Task
    10's `apply_refund_processed` only fires the pause/exhaust hook on a
    FULL refund) - so the derived estimate alone would still overstate
    spend. The ledger net must cap it."""
    client, session = api
    await _enable_ads(session)
    campaign, _placement, _creative = await _seed_campaign(
        session,
        price_paise=118000,
        pricing_model="cpm",
        budget_serves_total=5000,
        budget_serves_used=5000,  # fully consumed -> derived spend == price_paise
    )
    session.add(_ledger_entry(campaign, entry_type="ad_charge", amount_paise=118000))
    session.add(_ledger_entry(campaign, entry_type="ad_refund", amount_paise=-40000))
    await session.flush()

    resp = await client.get(f"/ads/my/campaigns/{campaign.id}/stats", headers=_as(OWNER))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["charged_net_paise"] == 78000  # 118000 - 40000
    assert body["spend_paise"] == 78000  # derived (118000) capped down to net


async def test_stats_no_ledger_rows_derived_spend_unchanged(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """A priced campaign that's been charged nothing YET (or a house
    campaign the real resolver can't find rows for) must fall back to the
    derived estimate untouched - `charged_net_paise` is None, never 0, so
    the route doesn't mistake "no data" for "fully refunded"."""
    client, session = api
    await _enable_ads(session)
    campaign, _placement, _creative = await _seed_campaign(
        session,
        price_paise=118000,
        pricing_model="cpm",
        budget_serves_total=5000,
        budget_serves_used=2500,
    )
    await session.flush()

    resp = await client.get(f"/ads/my/campaigns/{campaign.id}/stats", headers=_as(OWNER))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["charged_net_paise"] is None
    assert body["spend_paise"] == 59000  # 118000 * 2500 // 5000, untouched by any cap


async def test_stats_unregistered_charged_resolver_falls_back_to_derived(
    api: tuple[httpx.AsyncClient, AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed at the route level too: even with real ledger rows that
    WOULD cap spend, an unregistered/failing resolver must not block the
    route or zero out spend - it falls back to the derived estimate, same
    as shared.lookups.resolve_campaign_charged's own None contract."""
    client, session = api
    await _enable_ads(session)
    campaign, _placement, _creative = await _seed_campaign(
        session,
        price_paise=118000,
        pricing_model="cpm",
        budget_serves_total=5000,
        budget_serves_used=5000,
    )
    session.add(_ledger_entry(campaign, entry_type="ad_charge", amount_paise=118000))
    session.add(_ledger_entry(campaign, entry_type="ad_refund", amount_paise=-118000))
    await session.flush()

    async def _always_none(session: AsyncSession, campaign_id: uuid.UUID) -> int | None:
        return None

    monkeypatch.setattr(selfserve_router_module, "resolve_campaign_charged", _always_none)

    resp = await client.get(f"/ads/my/campaigns/{campaign.id}/stats", headers=_as(OWNER))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["charged_net_paise"] is None
    assert body["spend_paise"] == 118000  # derived, unconstrained by the (unreachable) ledger


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
