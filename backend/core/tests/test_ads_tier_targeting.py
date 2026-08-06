"""M5 Task 4: tier-targeted placements ("all T3 towns in TN") in the serve
path. `tiers` is a python-side FILTER next to `category_matches` - it is NOT
a geo rung (geo_match_rung stays untouched); fail closed: an unclassified
viewer (no pincode) never matches a tier-targeted placement."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from shared.db import get_session
from shared.lookups import BusinessRef, register_business_resolver
from shared.security import register_principal_resolver
from tests.test_ads_serve import (  # noqa: F401  (api/ads_redis re-exported as fixtures)
    CHENNAI_PINCODE,
    COIMBATORE_PINCODE,
    TN_STATE_LGD,
    UNKNOWN_PINCODE,
    _enable_ads,
    _seed_ad,
    ads_redis,
    api,
)

pytestmark = pytest.mark.asyncio


async def _upsert_tier(session: AsyncSession, pincode: str, tier: int) -> None:
    """Write a geo.pincode_tiers row via raw SQL (tests may; app code must not -
    the only sanctioned read is shared.geo.service.get_tier). Copied from
    tests/test_ads_pricing.py's helper of the same shape."""
    await session.execute(
        text(
            "INSERT INTO geo.pincode_tiers"
            " (id, pincode, population, population_grade, tier, computed_at)"
            " VALUES (gen_random_uuid(), :pincode, 1000, 'town', :tier, now())"
            " ON CONFLICT (pincode) DO UPDATE SET tier = EXCLUDED.tier,"
            " computed_at = EXCLUDED.computed_at"
        ),
        {"pincode": pincode, "tier": tier},
    )
    await session.flush()


async def test_tier_targeted_placement_serves_in_matching_tier(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _upsert_tier(session, COIMBATORE_PINCODE, 2)
    await _seed_ad(session, geo_target={"state": TN_STATE_LGD, "tiers": [2]})

    r = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": COIMBATORE_PINCODE}
    )
    assert r.status_code == 200, r.text
    assert r.json()["ad"] is not None


async def test_tier_targeted_placement_skipped_in_other_tier(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _upsert_tier(session, CHENNAI_PINCODE, 3)
    await _seed_ad(session, geo_target={"state": TN_STATE_LGD, "tiers": [2]})

    r = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": CHENNAI_PINCODE}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ad": None, "ads": []}


async def test_tier_targeted_placement_never_matches_without_pincode(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _seed_ad(session, geo_target={"tiers": [2]})

    r = await client.get("/ads/serve", params={"slot": "directory_browse"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ad": None, "ads": []}


async def test_unknown_pincode_defaults_tier4(
    api: tuple[httpx.AsyncClient, AsyncSession],
    tn_geo_sample: None,
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    await _seed_ad(session, geo_target={"tiers": [4]})

    r = await client.get(
        "/ads/serve", params={"slot": "directory_browse", "pincode": UNKNOWN_PINCODE}
    )
    assert r.status_code == 200, r.text
    assert r.json()["ad"] is not None


ADMIN = uuid.uuid4()
KNOWN_BUSINESS = uuid.uuid4()


def _as_staff() -> dict[str, str]:
    return {"x-test-user": str(ADMIN), "x-test-roles": "staff"}


async def _biz_resolver(session: AsyncSession, business_id: uuid.UUID) -> BusinessRef | None:
    if business_id == KNOWN_BUSINESS:
        return BusinessRef(id=business_id, owner_user_id=uuid.uuid4(), name="Kovai Mills")
    return None


@pytest.fixture
async def admin_client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    """Mirrors tests/test_ads_admin.py's `api` fixture (registers a principal +
    business resolver so /admin/ads/* is reachable) - a distinct fixture name
    here because this file also imports test_ads_serve's public-surface `api`
    fixture for the tier-matching tests above."""
    app = create_app()
    register_business_resolver(_biz_resolver)

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        if header is None:
            return None

        class _Principal:
            def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
                self.user_id = user_id
                self.roles = roles

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


async def test_geo_target_tiers_validation(admin_client: httpx.AsyncClient) -> None:
    campaign_r = await admin_client.post(
        "/admin/ads/campaigns",
        json={
            "advertiser_business_id": str(KNOWN_BUSINESS),
            "name": "Kovai Mills - kharif push",
            "flight_start": "2026-08-01",
            "flight_end": "2026-09-01",
        },
        headers=_as_staff(),
    )
    assert campaign_r.status_code == 201, campaign_r.text
    campaign_id = campaign_r.json()["id"]

    for bad_tiers in ([0], [1, 2, 3, 4, 5, 1], "x"):
        r = await admin_client.post(
            "/admin/ads/placements",
            json={
                "campaign_id": campaign_id,
                "slot_key": "directory_browse",
                "geo_target": {"tiers": bad_tiers},
                "weight": 1,
            },
            headers=_as_staff(),
        )
        assert r.status_code == 422, (bad_tiers, r.text)
