"""Tracking beacons (D21 Task 9): POST /ads/impressions, POST /ads/clicks.
Flag-gated (404 while dark), Redis SET NX EX 60 dedupe per viewer_hash +
placement, unknown placements 404 before anything is logged."""

import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.ads.models import Campaign, Click, Creative, Impression, Placement
from settings import get_settings
from shared.cache import reset_redis
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache

pytestmark = pytest.mark.asyncio

TEST_REDIS_DB = 9


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
    """Point shared.cache.get_redis at the flushed test redis DB (mirrors
    test_ads_serve.py's fixture) so dedupe keys don't leak across tests."""
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


async def _seed_placement(session: AsyncSession) -> Placement:
    today = date.today()
    campaign = Campaign(
        advertiser_business_id=uuid.uuid4(),
        name="Kovai Mills - kharif push",
        status="active",
        flight_start=today - timedelta(days=1),
        flight_end=today + timedelta(days=30),
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
    placement = Placement(
        campaign_id=campaign.id,
        slot_key="directory_browse",
        geo_target={},
        weight=1,
    )
    session.add(placement)
    await session.flush()
    return placement


def _body(placement: Placement) -> dict[str, str]:
    return {
        "placement_id": str(placement.id),
        "creative_id": str(uuid.uuid4()),
        "slot_key": "directory_browse",
    }


@pytest.mark.parametrize("path", ["/ads/impressions", "/ads/clicks"])
async def test_flag_off_beacon_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
    ads_redis: Redis,
    path: str,
) -> None:
    client, session = api
    placement = await _seed_placement(session)
    r = await client.post(path, json=_body(placement))
    assert r.status_code == 404


async def test_impression_happy_path_inserts_row(
    api: tuple[httpx.AsyncClient, AsyncSession],
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    placement = await _seed_placement(session)

    r = await client.post("/ads/impressions", json=_body(placement))
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ok"}

    count = await session.scalar(select(func.count()).select_from(Impression))
    assert count == 1


async def test_impression_duplicate_within_window_no_second_row(
    api: tuple[httpx.AsyncClient, AsyncSession],
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    placement = await _seed_placement(session)
    body = _body(placement)

    first = await client.post("/ads/impressions", json=body)
    assert first.json() == {"status": "ok"}

    second = await client.post("/ads/impressions", json=body)
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}

    count = await session.scalar(select(func.count()).select_from(Impression))
    assert count == 1


async def test_click_happy_path_inserts_row(
    api: tuple[httpx.AsyncClient, AsyncSession],
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    placement = await _seed_placement(session)

    r = await client.post("/ads/clicks", json=_body(placement))
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ok"}

    count = await session.scalar(select(func.count()).select_from(Click))
    assert count == 1


async def test_click_duplicate_within_window_no_second_row(
    api: tuple[httpx.AsyncClient, AsyncSession],
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    placement = await _seed_placement(session)
    body = _body(placement)

    first = await client.post("/ads/clicks", json=body)
    assert first.json() == {"status": "ok"}

    second = await client.post("/ads/clicks", json=body)
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}

    count = await session.scalar(select(func.count()).select_from(Click))
    assert count == 1


@pytest.mark.parametrize("path", ["/ads/impressions", "/ads/clicks"])
async def test_unknown_placement_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
    ads_redis: Redis,
    path: str,
) -> None:
    client, session = api
    await _enable_ads(session)
    body = {
        "placement_id": str(uuid.uuid4()),
        "creative_id": str(uuid.uuid4()),
        "slot_key": "directory_browse",
    }
    r = await client.post(path, json=body)
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown_placement"


async def test_different_viewer_lands_second_row(
    api: tuple[httpx.AsyncClient, AsyncSession],
    ads_redis: Redis,
) -> None:
    client, session = api
    await _enable_ads(session)
    placement = await _seed_placement(session)
    body = _body(placement)

    first = await client.post("/ads/impressions", json=body)
    assert first.json() == {"status": "ok"}

    second = await client.post("/ads/impressions", json=body, headers={"user-agent": "other"})
    assert second.json() == {"status": "ok"}

    count = await session.scalar(select(func.count()).select_from(Impression))
    assert count == 2
