"""NON-NEGOTIABLES 1+2: every served ad carries label="sponsored" on the
wire; geo targeting matches ONLY in-scope locations (the 641001 test).
Also: flag-off 404, freq cap, weighted rotation, locale fallback."""

import random
import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.ads import service
from modules.ads.models import Campaign, Creative, Placement
from modules.directory import service as directory_service
from modules.directory.models import Business
from settings import get_settings
from shared.cache import reset_redis
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache
from shared.geo.models import District, Pincode

pytestmark = pytest.mark.asyncio

TEST_REDIS_DB = 9
COIMBATORE_DISTRICT_LGD = 569
TN_STATE_LGD = 33
COIMBATORE_PINCODE = "641001"
CHENNAI_PINCODE = "600001"
UNKNOWN_PINCODE = "999999"
DELHI_PINCODE = "110001"  # M3 NN1: valid shape, resolves to no TN district


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client, db_session


@pytest.fixture
async def ads_redis(redis_client: Redis, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Redis]:
    """Point shared.cache.get_redis at the flushed test redis DB (mirrors the
    otp_redis fixture pattern in test_otp_throttle.py)."""
    url = get_settings().redis_url.rsplit("/", 1)[0] + f"/{TEST_REDIS_DB}"
    monkeypatch.setenv("REDIS_URL", url)
    get_settings.cache_clear()
    reset_redis()
    yield redis_client


async def _enable_ads(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "ads_enabled")
    assert flag is not None
    flag.enabled = True
    await session.flush()
    reset_flag_cache()


async def _split_chennai_district(session: AsyncSession) -> None:
    """tn_geo_sample seeds both 641001 and 600001 under the single Coimbatore
    district row - fine for the covers() tests it was built for, but the
    district-targeting non-negotiable needs 600001 resolving to a DIFFERENT
    district. Give Chennai its own district row here (test-local only; the
    shared fixture is out of scope for this task)."""
    district = await session.scalar(
        select(District).where(District.lgd_code == COIMBATORE_DISTRICT_LGD)
    )
    assert district is not None
    chennai_district = District(lgd_code=999, state_id=district.state_id, name="Chennai")
    session.add(chennai_district)
    await session.flush()
    await session.execute(
        update(Pincode)
        .where(Pincode.pincode == CHENNAI_PINCODE)
        .values(district_id=chennai_district.id)
    )
    await session.flush()


async def _advertiser(session: AsyncSession) -> uuid.UUID:
    """A real, active directory business: serve-time is_servable (M1.5.E) is
    fail-closed, so a dangling advertiser id would never serve."""
    business = await directory_service.create_business(
        session,
        owner_user_id=uuid.uuid4(),
        name=f"Advertiser {uuid.uuid4().hex[:8]}",
        type_="shop",
        primary_pincode=COIMBATORE_PINCODE,
    )
    return business.id


async def _seed_ad(
    session: AsyncSession,
    *,
    geo_target: dict[str, object],
    weight: int = 1,
    slot_key: str = "directory_browse",
    copy: dict[str, dict[str, str]] | None = None,
    moderation_status: str = "approved",
    campaign_status: str = "active",
    target_url: str = "https://kovaimills.example.com/offers",
) -> Placement:
    today = date.today()
    campaign = Campaign(
        advertiser_business_id=await _advertiser(session),
        name="Kovai Mills - kharif push",
        status=campaign_status,
        flight_start=today - timedelta(days=1),
        flight_end=today + timedelta(days=30),
    )
    session.add(campaign)
    await session.flush()
    creative = Creative(
        campaign_id=campaign.id,
        media_keys=["ads/creative-1.jpg"],
        copy=copy or {"en": {"title": "Kharif seeds now live", "body": "Book your order today."}},
        target_url=target_url,
        moderation_status=moderation_status,
    )
    session.add(creative)
    placement = Placement(
        campaign_id=campaign.id,
        slot_key=slot_key,
        geo_target=geo_target,
        weight=weight,
    )
    session.add(placement)
    await session.flush()
    return placement


async def test_flag_off_serve_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, _ = api
    r = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
    )
    assert r.status_code == 404


async def test_serve_carries_sponsored_label(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _split_chennai_district(session)
    await _seed_ad(session, geo_target={"district": COIMBATORE_DISTRICT_LGD})
    r = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ad"]["label"] == "sponsored"
    assert body["ad"]["target_url"] == "https://kovaimills.example.com/offers"


async def test_geo_district_placement_serves_641001_not_600001(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _split_chennai_district(session)
    await _seed_ad(session, geo_target={"district": COIMBATORE_DISTRICT_LGD})

    hit = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
    )
    assert hit.status_code == 200
    assert hit.json()["ad"] is not None

    miss = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": CHENNAI_PINCODE}
    )
    assert miss.status_code == 200
    assert miss.json() == {"ad": None, "ads": []}


async def test_suspended_advertiser_ads_stop_serving(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    """M1.5 threat model: a suspended vendor's ads must not keep serving.
    Serve-time is_servable check (the M3 seam, live already)."""
    client, session = api
    await _enable_ads(session)
    await _split_chennai_district(session)
    placement = await _seed_ad(session, geo_target={"district": COIMBATORE_DISTRICT_LGD})

    hit = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
    )
    assert hit.status_code == 200
    assert hit.json()["ad"] is not None

    campaign = await session.get(Campaign, placement.campaign_id)
    assert campaign is not None
    business = await session.get(Business, campaign.advertiser_business_id)
    assert business is not None
    business.status = "suspended"
    await session.flush()

    miss = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
    )
    assert miss.status_code == 200
    assert miss.json() == {"ad": None, "ads": []}


async def test_geo_pincode_list_and_state_and_empty(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _split_chennai_district(session)

    await _seed_ad(
        session, geo_target={"pincodes": [COIMBATORE_PINCODE]}, slot_key="directory_browse"
    )
    hit = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
    )
    assert hit.json()["ad"] is not None
    miss = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": CHENNAI_PINCODE}
    )
    assert miss.json()["ad"] is None


async def test_geo_state_matches_both_tn_pincodes(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _split_chennai_district(session)
    await _seed_ad(session, geo_target={"state": TN_STATE_LGD})

    for pincode in (COIMBATORE_PINCODE, CHENNAI_PINCODE):
        r = await client.get("/ads/serve", params={"slot": "directory_browse", "pincode": pincode})
        assert r.json()["ad"] is not None, pincode


async def test_geo_empty_target_matches_any_including_unknown_pincode(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _seed_ad(session, geo_target={})

    r = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": UNKNOWN_PINCODE}
    )
    assert r.status_code == 200
    assert r.json()["ad"] is not None


async def test_unknown_pincode_only_untargeted(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _split_chennai_district(session)
    await _seed_ad(session, geo_target={"district": COIMBATORE_DISTRICT_LGD})

    r = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": UNKNOWN_PINCODE}
    )
    assert r.status_code == 200
    assert r.json() == {"ad": None, "ads": []}


async def test_pending_creative_never_serves(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _seed_ad(session, geo_target={}, moderation_status="pending")

    r = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
    )
    assert r.status_code == 200
    assert r.json() == {"ad": None, "ads": []}


async def test_freq_cap_skips_exhausted_placement(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _seed_ad(session, geo_target={})

    cap = get_settings().ads_freq_cap_per_day
    assert cap == 3
    for _ in range(cap):
        r = await client.get(
            "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
        )
        assert r.json()["ad"] is not None

    exhausted = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
    )
    assert exhausted.status_code == 200
    assert exhausted.json() == {"ad": None, "ads": []}


async def test_share_of_voice_weighted_rotation(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session = api
    await _enable_ads(session)
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1000")
    get_settings.cache_clear()

    light = await _seed_ad(session, geo_target={}, weight=1)
    heavy = await _seed_ad(session, geo_target={}, weight=3)

    import modules.ads.router as router_module

    monkeypatch.setattr(router_module, "_rng", random.Random(42))

    async def _always_true(*args: object, **kwargs: object) -> bool:
        return True

    monkeypatch.setattr(service, "under_freq_cap", _always_true)

    heavy_hits = 0
    total = 200
    for _ in range(total):
        r = await client.get(
            "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
        )
        assert r.status_code == 200
        placement_id = r.json()["ad"]["placement_id"]
        if placement_id == str(heavy.id):
            heavy_hits += 1
        else:
            assert placement_id == str(light.id)

    ratio = heavy_hits / total
    assert 0.55 <= ratio <= 0.90, ratio


async def test_locale_fallback(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _seed_ad(
        session,
        geo_target={},
        copy={"en": {"title": "Kharif seeds now live", "body": "Book your order today."}},
    )

    r = await client.get(
        "/ads/serve",
        params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE, "locale": "ta"},
    )
    assert r.status_code == 200
    assert r.json()["ad"]["title"] == "Kharif seeds now live"


async def test_bad_slot_422(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    r = await client.get(
        "/ads/serve", params={"slot": "homepage_hero", "pincode": COIMBATORE_PINCODE}
    )
    assert r.status_code == 422


# --- M2 (SPEC M2): milk slots, category targeting, multi-creative serve ---


async def test_milk_slot_keys_are_registered(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    for slot in (
        "milk_global_header",
        "milk_home_hero",
        "milk_category_banner",
        "milk_search_inline",
        "milk_profile_footer",
    ):
        await _seed_ad(session, geo_target={}, slot_key=slot)
        r = await client.get("/ads/serve", params={"slot": slot, "pincode": COIMBATORE_PINCODE})
        assert r.status_code == 200, (slot, r.text)
        assert r.json()["ad"] is not None, slot


async def test_serve_count_returns_distinct_placements(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    for _ in range(3):
        await _seed_ad(session, geo_target={}, slot_key="milk_global_header")
    r = await client.get(
        "/ads/serve",
        params={"slot": "milk_global_header", "pincode": COIMBATORE_PINCODE, "count": 5},
    )
    assert r.status_code == 200
    body = r.json()
    ids = [ad["placement_id"] for ad in body["ads"]]
    assert len(ids) == 3 and len(set(ids)) == 3
    assert body["ad"] == body["ads"][0]  # legacy single-ad shape stays intact


async def test_category_targeting(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _seed_ad(session, geo_target={"categories": ["ghee"]}, slot_key="milk_category_banner")
    hit = await client.get(
        "/ads/serve",
        params={"slot": "milk_category_banner", "pincode": COIMBATORE_PINCODE, "category": "ghee"},
    )
    assert hit.status_code == 200, hit.text
    assert hit.json()["ad"] is not None
    miss = await client.get(
        "/ads/serve",
        params={"slot": "milk_category_banner", "pincode": COIMBATORE_PINCODE, "category": "milk"},
    )
    assert miss.json()["ad"] is None
    no_ctx = await client.get(
        "/ads/serve", params={"slot": "milk_category_banner", "pincode": COIMBATORE_PINCODE}
    )
    assert no_ctx.json()["ad"] is None  # category-targeted needs category context


async def test_serve_without_pincode_only_untargeted_geo(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _seed_ad(session, geo_target={"district": COIMBATORE_DISTRICT_LGD})
    r = await client.get("/ads/serve", params={"slot": "directory_browse"})
    assert r.status_code == 200, r.text
    assert r.json()["ad"] is None  # unknown viewer location never matches geo targeting
    await _seed_ad(session, geo_target={})
    r = await client.get("/ads/serve", params={"slot": "directory_browse"})
    assert r.json()["ad"] is not None


# --- M3 (SPEC M3): global+local blend, local boost, category independence ---


async def test_blend_global_and_local_serve_together(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    """NON-NEGOTIABLE 1: an ALL-pincode (global) campaign and a 641001-local
    campaign BOTH serve at 641001; the local one is absent at 110001."""
    client, session = api
    await _enable_ads(session)
    global_p = await _seed_ad(session, geo_target={})
    local_p = await _seed_ad(session, geo_target={"pincodes": [COIMBATORE_PINCODE]})

    at_local = await client.get(
        "/ads/serve",
        params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE, "count": 5},
    )
    assert at_local.status_code == 200, at_local.text
    local_ids = {ad["placement_id"] for ad in at_local.json()["ads"]}
    assert {str(global_p.id), str(local_p.id)} <= local_ids

    at_remote = await client.get(
        "/ads/serve",
        params={"slot": "directory_browse", "pincode": DELHI_PINCODE, "count": 5},
    )
    remote_ids = {ad["placement_id"] for ad in at_remote.json()["ads"]}
    assert str(local_p.id) not in remote_ids
    assert str(global_p.id) in remote_ids


async def test_local_boost_share_of_voice(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M3.A: equal placement weights, but the 641001-targeted placement gets
    the default 2x local boost -> ~2/3 of single-ad serves."""
    client, session = api
    await _enable_ads(session)
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1000")
    get_settings.cache_clear()

    await _seed_ad(session, geo_target={}, weight=1)
    local = await _seed_ad(session, geo_target={"pincodes": [COIMBATORE_PINCODE]}, weight=1)

    import modules.ads.router as router_module

    monkeypatch.setattr(router_module, "_rng", random.Random(42))

    async def _always_true(*args: object, **kwargs: object) -> bool:
        return True

    monkeypatch.setattr(service, "under_freq_cap", _always_true)

    local_hits = 0
    total = 200
    for _ in range(total):
        r = await client.get(
            "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
        )
        assert r.status_code == 200
        if r.json()["ad"]["placement_id"] == str(local.id):
            local_hits += 1

    ratio = local_hits / total
    assert 0.55 <= ratio <= 0.80, ratio


async def test_budget_exhaustion_stops_serving(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    """M3.A in-budget: a 2-credit campaign serves exactly twice, then the SQL
    predicate excludes it and `used` never exceeds `total`."""
    client, session = api
    await _enable_ads(session)
    placement = await _seed_ad(session, geo_target={})
    campaign = await session.get(Campaign, placement.campaign_id)
    assert campaign is not None
    campaign.budget_serves_total = 2
    await session.flush()

    results = []
    for _ in range(3):
        r = await client.get(
            "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
        )
        assert r.status_code == 200
        results.append(r.json()["ads"])
    assert results[0] and results[1]  # two credits -> two serves
    assert results[2] == []  # out of budget -> excluded
    await session.refresh(campaign)
    assert campaign.budget_serves_used == 2


async def test_ghee_campaign_never_serves_on_paneer_page(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    """NON-NEGOTIABLE 2: the category dimension is evaluated independently
    per slot instance - a ghee campaign never serves on a paneer page."""
    client, session = api
    await _enable_ads(session)
    ghee_p = await _seed_ad(
        session, geo_target={"categories": ["ghee"]}, slot_key="milk_category_banner"
    )

    paneer = await client.get(
        "/ads/serve",
        params={
            "slot": "milk_category_banner",
            "pincode": COIMBATORE_PINCODE,
            "category": "paneer",
            "count": 5,
        },
    )
    assert str(ghee_p.id) not in {ad["placement_id"] for ad in paneer.json()["ads"]}

    ghee = await client.get(
        "/ads/serve",
        params={
            "slot": "milk_category_banner",
            "pincode": COIMBATORE_PINCODE,
            "category": "ghee",
            "count": 5,
        },
    )
    assert str(ghee_p.id) in {ad["placement_id"] for ad in ghee.json()["ads"]}


async def test_pending_creative_never_serves_on_milk_slot(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    """M2 NON-NEGOTIABLE 1: unapproved/pending creative NEVER renders."""
    client, session = api
    await _enable_ads(session)
    await _seed_ad(
        session, geo_target={}, slot_key="milk_global_header", moderation_status="pending"
    )
    r = await client.get(
        "/ads/serve",
        params={"slot": "milk_global_header", "pincode": COIMBATORE_PINCODE, "count": 5},
    )
    assert r.status_code == 200
    assert r.json()["ad"] is None and r.json()["ads"] == []
